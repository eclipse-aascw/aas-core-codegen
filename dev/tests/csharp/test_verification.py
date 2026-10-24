import os
import pathlib
import unittest

from aas_core_codegen import intermediate
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.common import LinenoColumner, Error
from aas_core_codegen.csharp import (
    common as csharp_common,
    lib as csharp_lib,
)
from aas_core_codegen import parse

import tests.common


class Test_against_recorded(unittest.TestCase):
    def test_cases(self) -> None:
        repo_dir = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent.parent

        parent_case_dir = repo_dir / "dev/test_data/csharp/test_verification"
        assert parent_case_dir.exists() and parent_case_dir.is_dir(), parent_case_dir

        for model_pth in sorted(parent_case_dir.glob("**/meta_model.py")):
            text = model_pth.read_text(encoding="utf-8")
            atok, parse_exception = parse.source_to_atok(source=text)
            assert (
                parse_exception is None
            ), f"Unexpected parse exception in {model_pth}: {parse_exception=}"
            assert atok is not None

            lineno_columner = LinenoColumner(atok=atok)
            parsed_symbol_table, error = parse.atok_to_symbol_table(atok=atok)

            assert error is None, (
                f"Unexpected error in parsing {model_pth}: "
                f"{lineno_columner.error_message(error)}"
            )
            assert parsed_symbol_table is not None

            ir_symbol_table, error = intermediate.translate(
                parsed_symbol_table=parsed_symbol_table,
                atok=atok,
            )

            assert error is None, (
                f"Unexpected error in translating {model_pth} to intermediate: "
                f"{lineno_columner.error_message(error)}"
            )
            assert ir_symbol_table is not None

            type_inference, inference_errors = intermediate_type_inference.infer(
                symbol_table=ir_symbol_table
            )
            if inference_errors is not None:
                joined_error = Error(
                    None, "Inferring the types failed", inference_errors
                )
                raise AssertionError(
                    f"Unexpected errors in inferring the types "
                    f"for {model_pth}: {lineno_columner.error_message(joined_error)}"
                )
            assert type_inference is not None

            code, errors = csharp_lib.generate_verification(
                symbol_table=ir_symbol_table,
                type_inference=type_inference,
                namespace=csharp_common.NamespaceIdentifier("dummyNamespace"),
                spec_impls=dict(),
            )
            if errors is not None:
                joined_error = Error(
                    None, "Generating verification code failed", errors
                )
                raise AssertionError(
                    f"Unexpected errors in generating verification code "
                    f"for {model_pth}: {lineno_columner.error_message(joined_error)}"
                )
            assert code is not None

            expected_pth = model_pth.parent / "expected_verification.cs"
            if tests.common.RERECORD:
                expected_pth.write_text(code, encoding="utf-8")
            else:
                try:
                    expected_code = expected_pth.read_text(encoding="utf-8")
                except Exception as exception:
                    raise RuntimeError(
                        f"Failed to read the expected code from {expected_pth}"
                    ) from exception

                self.assertEqual(expected_code, code)


if __name__ == "__main__":
    unittest.main()
