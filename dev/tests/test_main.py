# pylint: disable=missing-docstring

import ast
import contextlib
import difflib
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from typing import List, MutableMapping, Set

import aas_core_codegen.main
import tests.common

_REPO_DIR = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

_COMMON_META_MODEL_STEM_TO_PATH = {
    model_path.stem: model_path for model_path in tests.common.COMMON_META_MODEL_PATHS
}


class _TestCase(unittest.TestCase):
    def _run_expected_test(
        self, target: aas_core_codegen.main.Target, case_name: str
    ) -> None:
        target_dir = _REPO_DIR / "dev" / "test_data" / "main" / target.value
        assert target_dir.exists() and target_dir.is_dir(), target_dir

        case_dir = target_dir / "expected" / case_name

        assert case_dir.exists() and case_dir.is_dir(), case_dir

        meta_model_path = case_dir / "meta_model.py"
        if not meta_model_path.exists():
            real_meta_model_path = _COMMON_META_MODEL_STEM_TO_PATH.get(case_name, None)

            if real_meta_model_path is None:
                raise RuntimeError(
                    f"The meta-model could not be found for target {target.value} "
                    f"and case {case_name}. Neither {meta_model_path} exists "
                    f"nor is there a real meta-model corresponding to it. "
                    f"The real meta-model paths "
                    f"are: {tests.common.COMMON_META_MODEL_PATHS}."
                )
            else:
                meta_model_path = real_meta_model_path

        assert meta_model_path.exists() and meta_model_path.is_file(), meta_model_path

        snippets_dir = case_dir / "input/snippets"
        assert snippets_dir.exists() and snippets_dir.is_dir(), snippets_dir

        expected_output_dir = case_dir / "expected_output"

        with contextlib.ExitStack() as exit_stack:
            if tests.common.RERECORD:
                output_dir = expected_output_dir

                # NOTE (mristin):
                # We add this check to make sure we do not delete anything
                # important.
                assert output_dir.name == "expected_output"

                shutil.rmtree(expected_output_dir, ignore_errors=True)

                expected_output_dir.mkdir(exist_ok=True, parents=True)
            else:
                assert expected_output_dir.exists() and expected_output_dir.is_dir(), (
                    f"The environment variable "
                    f"{tests.common.RERECORD_ENVIRONMENT_VARIABLE_NAME} has not been "
                    f"set, so no output will be re-recorded and has to be tested "
                    f"against the golden previously recorded output, but the directory "
                    f"to the expected output either does not exist or "
                    f"is not a directory: {expected_output_dir}"
                )

                # pylint: disable=consider-using-with
                tmp_dir = tempfile.TemporaryDirectory()
                exit_stack.push(tmp_dir)
                output_dir = pathlib.Path(tmp_dir.name)

            params = aas_core_codegen.main.Parameters(
                model_path=meta_model_path,
                target=target,
                snippets_dir=snippets_dir,
                output_dir=output_dir,
                cache_model=tests.common.CACHE_MAIN_MODELS,
            )

            stdout = io.StringIO()
            stderr = io.StringIO()

            return_code = aas_core_codegen.main.execute(
                params=params, stdout=stdout, stderr=stderr
            )

            if stderr.getvalue() != "":
                raise AssertionError(
                    f"Expected no stderr on valid models, but got:\n"
                    f"{stderr.getvalue()}"
                )

            self.assertEqual(0, return_code, "Expected 0 return code on valid models")

            normalized_stdout = stdout.getvalue().replace(
                str(output_dir), "<output dir>"
            )

            if tests.common.RERECORD:
                stdout_pth = expected_output_dir / "stdout.txt"
                stdout_pth.write_text(normalized_stdout, encoding="utf-8")

            if not tests.common.RERECORD:
                tests.common.assert_got_as_expected_output_dir(
                    output_dir=output_dir,
                    expected_output_dir=expected_output_dir,
                    normalized_stdout=normalized_stdout,
                )

    def _run_unexpected_test(
        self, target: aas_core_codegen.main.Target, case_name: str
    ) -> None:
        target_dir = _REPO_DIR / "dev" / "test_data" / "main" / target.value
        assert target_dir.exists() and target_dir.is_dir(), target_dir

        case_dir = target_dir / "unexpected" / case_name

        assert case_dir.exists() and case_dir.is_dir(), case_dir

        meta_model_path = case_dir / "meta_model.py"

        assert meta_model_path.exists() and meta_model_path.is_file(), meta_model_path

        snippets_dir = case_dir / "input/snippets"
        assert snippets_dir.exists() and snippets_dir.is_dir(), snippets_dir

        expected_output_dir = case_dir / "expected_output"

        with contextlib.ExitStack() as exit_stack:
            # NOTE (mristin):
            # We do not store the output as it is meaningless -- the return
            # code will not be zero, so the output should be disregarded by
            # the end user.

            # pylint: disable=consider-using-with
            tmp_dir = tempfile.TemporaryDirectory()
            exit_stack.push(tmp_dir)
            output_dir = pathlib.Path(tmp_dir.name)

            params = aas_core_codegen.main.Parameters(
                model_path=meta_model_path,
                target=target,
                snippets_dir=snippets_dir,
                output_dir=output_dir,
                cache_model=tests.common.CACHE_MAIN_MODELS,
            )

            stdout = io.StringIO()
            stderr = io.StringIO()

            return_code = aas_core_codegen.main.execute(
                params=params, stdout=stdout, stderr=stderr
            )

            self.assertNotEqual(
                0, return_code, "Expected non-zero return code on invalid inputs"
            )

            normalized_stdout = (
                stdout.getvalue()
                .replace(str(output_dir), "<output dir>")
                .replace(str(meta_model_path), f"<path to {meta_model_path.name}>")
            )

            normalized_stderr = (
                stderr.getvalue()
                .replace(str(output_dir), "<output dir>")
                .replace(str(meta_model_path), f"<path to {meta_model_path.name}>")
            )

            expected_stdout_path = expected_output_dir / "stdout.txt"
            expected_stderr_path = expected_output_dir / "stderr.txt"
            expected_return_code_path = expected_output_dir / "return_code.json"

            if tests.common.RERECORD:
                expected_stdout_path.write_text(normalized_stdout, encoding="utf-8")
                expected_stderr_path.write_text(normalized_stderr, encoding="utf-8")
                expected_return_code_path.write_text(
                    json.dumps(return_code), encoding="utf-8"
                )

            else:
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
                    raise AssertionError(
                        f"Mismatch against {expected_stdout_path}:\n{diff}"
                    )

                try:
                    expected_stderr = expected_stderr_path.read_text(encoding="utf-8")
                except Exception as exception:
                    raise RuntimeError(
                        f"Failed to read expected stderr from {expected_stderr_path}"
                    ) from exception

                if normalized_stderr != expected_stderr:
                    diff = "\n".join(
                        difflib.unified_diff(
                            expected_stderr.splitlines(keepends=True),
                            normalized_stderr.splitlines(keepends=True),
                            fromfile=str(expected_stderr_path),
                            tofile="<actual stderr>",
                        )
                    )
                    raise AssertionError(
                        f"Mismatch against {expected_stderr_path}:\n{diff}"
                    )

                try:
                    expected_return_code = json.loads(
                        expected_return_code_path.read_text(encoding="utf-8")
                    )
                except Exception as exception:
                    raise RuntimeError(
                        f"Failed to read expected return code "
                        f"from {expected_return_code_path}"
                    ) from exception

                self.assertEqual(expected_return_code, return_code, case_dir)


class Test_cpp(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="aas_core_meta.v3"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="constrained_primitives"
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="deep_class_hierarchy"
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="list_of_classes"
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="list_of_enums"
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="list_of_primitives"
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="primitive_types"
        )

    def test_expected_problematic_keywords(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="problematic_keywords"
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CPP, case_name="tuples"
        )

    def test_unexpected_conflict_between_constructor_arguments(self) -> None:
        self._run_unexpected_test(
            target=aas_core_codegen.main.Target.CPP,
            case_name="conflict_between_constructor_arguments",
        )


class Test_csharp(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="aas_core_meta.v3"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP,
            case_name="constrained_primitives",
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="deep_class_hierarchy"
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="list_of_classes"
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="list_of_enums"
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="list_of_primitives"
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="primitive_types"
        )

    def test_expected_problematic_keywords(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="problematic_keywords"
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.CSHARP, case_name="tuples"
        )

    def test_unexpected_conflict_between_transformed_keyword_and_property(self) -> None:
        self._run_unexpected_test(
            target=aas_core_codegen.main.Target.CSHARP,
            case_name="conflict_between_transformed_keyword_and_property",
        )


class Test_golang(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="aas_core_meta.v3"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG,
            case_name="constrained_primitives",
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="deep_class_hierarchy"
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="list_of_classes"
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="list_of_enums"
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="list_of_primitives"
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="primitive_types"
        )

    def test_expected_problematic_keywords(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="problematic_keywords"
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.GOLANG, case_name="tuples"
        )

    def test_unexpected_conflict_between_transformed_keyword_and_property(self) -> None:
        self._run_unexpected_test(
            target=aas_core_codegen.main.Target.GOLANG,
            case_name="conflict_between_transformed_keyword_and_property",
        )


class Test_java(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="aas_core_meta.v3"
        )

    def test_expected_constants(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="constants"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA,
            case_name="constrained_primitives",
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="deep_class_hierarchy"
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="list_of_classes"
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="list_of_enums"
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="list_of_primitives"
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="primitive_types"
        )

    def test_expected_problematic_keywords(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="problematic_keywords"
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JAVA, case_name="tuples"
        )

    def test_unexpected_conflict_between_constructor_arguments(self) -> None:
        self._run_unexpected_test(
            target=aas_core_codegen.main.Target.JAVA,
            case_name="conflict_between_constructor_arguments",
        )


class Test_jsonschema(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA, case_name="aas_core_meta.v3"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="constrained_primitives",
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="deep_class_hierarchy",
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_classes",
        )

    def test_expected_list_of_classes_with_invariants(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_classes_with_invariants",
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_enums",
        )

    def test_expected_list_of_lists_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_lists_of_classes",
        )

    def test_expected_list_of_lists_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_lists_of_constrained_primitives",
        )

    def test_expected_list_of_lists_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_lists_of_enums",
        )

    def test_expected_list_of_lists_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_lists_of_primitives",
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_primitives",
        )

    def test_expected_list_of_primitives_with_invariants(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="list_of_primitives_with_invariants",
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA, case_name="primitive_types"
        )

    def test_expected_regression_when_len_constraints_on_inherited_property(
        self,
    ) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA,
            case_name="regression_when_len_constraints_on_inherited_property",
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.JSONSCHEMA, case_name="tuples"
        )


class Test_python(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="aas_core_meta.v3"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON,
            case_name="constrained_primitives",
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="deep_class_hierarchy"
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="list_of_classes"
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="list_of_enums"
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="list_of_primitives"
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="primitive_types"
        )

    def test_expected_problematic_keywords(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="problematic_keywords"
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.PYTHON, case_name="tuples"
        )

    def test_unexpected_conflict_between_constructor_arguments(self) -> None:
        self._run_unexpected_test(
            target=aas_core_codegen.main.Target.PYTHON,
            case_name="conflict_between_constructor_arguments",
        )


class Test_typescript(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT, case_name="aas_core_meta.v3"
        )

    def test_expected_conflict_with_utility_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="conflict_with_utility_types",
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="constrained_primitives",
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="deep_class_hierarchy",
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="enum",
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="list_of_classes",
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="list_of_enums",
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="list_of_primitives",
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT, case_name="primitive_types"
        )

    def test_expected_problematic_keywords(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="problematic_keywords",
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT, case_name="tuples"
        )

    def test_unexpected_conflict_between_constructor_arguments(self) -> None:
        self._run_unexpected_test(
            target=aas_core_codegen.main.Target.TYPESCRIPT,
            case_name="conflict_between_constructor_arguments",
        )


class Test_xsd(_TestCase):
    def test_expected_aas_core_meta_v3(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="aas_core_meta.v3"
        )

    def test_expected_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="constrained_primitives"
        )

    def test_expected_custom_serialization_names(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="custom_serialization_names",
        )

    def test_expected_deep_class_hierarchy(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="deep_class_hierarchy"
        )

    def test_expected_empty_class(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="empty_class"
        )

    def test_expected_enum(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="enum"
        )

    def test_expected_list_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="list_of_classes"
        )

    def test_expected_list_of_classes_with_invariants(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_classes_with_invariants",
        )

    def test_expected_list_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_constrained_primitives",
        )

    def test_expected_list_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="list_of_enums"
        )

    def test_expected_list_of_lists_of_classes(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_lists_of_classes",
        )

    def test_expected_list_of_lists_of_constrained_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_lists_of_constrained_primitives",
        )

    def test_expected_list_of_lists_of_enums(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_lists_of_enums",
        )

    def test_expected_list_of_lists_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_lists_of_primitives",
        )

    def test_expected_list_of_primitives(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="list_of_primitives"
        )

    def test_expected_list_of_primitives_with_invariants(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="list_of_primitives_with_invariants",
        )

    def test_expected_primitive_types(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="primitive_types"
        )

    def test_expected_regression_when_len_constraints_on_inherited_property(
        self,
    ) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD,
            case_name="regression_when_len_constraints_on_inherited_property",
        )

    def test_expected_tuples(self) -> None:
        self._run_expected_test(
            target=aas_core_codegen.main.Target.XSD, case_name="tuples"
        )


class _CaseSpec:
    """Specify a single test."""

    target: aas_core_codegen.main.Target
    expected: bool
    name: str

    def __init__(
        self, target: aas_core_codegen.main.Target, expected: bool, name: str
    ) -> None:
        self.target = target
        self.expected = expected
        self.name = name


_TARGET_FROM_VALUE = {target.value: target for target in aas_core_codegen.main.Target}


def _assert_all_targets_covered() -> None:
    cases = []  # type: List[_CaseSpec]

    main_dir = _REPO_DIR / "dev" / "test_data" / "main"

    for target_dir in sorted(path for path in main_dir.iterdir() if path.is_dir()):
        if target_dir.stem not in _TARGET_FROM_VALUE:
            target_values_joined = ", ".join(
                target.value for target in aas_core_codegen.main.Target
            )
            raise RuntimeError(
                f"Unexpected directory not corresponding "
                f"to any target in {main_dir}: {target_dir}; "
                f"expected targets: {target_values_joined}"
            )

        target = _TARGET_FROM_VALUE[target_dir.stem]

        expected_dir = target_dir / "expected"
        if expected_dir.exists():
            assert expected_dir.is_dir(), expected_dir

            for case_name in sorted(
                path.name for path in expected_dir.iterdir() if path.is_dir()
            ):
                cases.append(_CaseSpec(target=target, expected=True, name=case_name))

        unexpected_dir = target_dir / "unexpected"
        if unexpected_dir.exists():
            assert unexpected_dir.is_dir(), unexpected_dir

            for case_name in sorted(
                path.stem for path in unexpected_dir.iterdir() if path.is_dir()
            ):
                cases.append(_CaseSpec(target=target, expected=False, name=case_name))

    # NOTE (mristin):
    # We parse this module using AST to validate test structure and enforce order.
    current_module_path = pathlib.Path(__file__)
    with open(current_module_path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    cases_by_target: MutableMapping[aas_core_codegen.main.Target, List[_CaseSpec]] = {}
    for case in cases:
        if case.target not in cases_by_target:
            cases_by_target[case.target] = []

        cases_by_target[case.target].append(case)

    targets_with_tests = []  # type: List[aas_core_codegen.main.Target]
    set_of_targets_with_tests = set()  # type: Set[aas_core_codegen.main.Target]

    for case in cases:
        if case.target not in set_of_targets_with_tests:
            targets_with_tests.append(case.target)
            set_of_targets_with_tests.add(case.target)

    class_nodes = [
        node for node in tree.body if isinstance(node, ast.ClassDef)
    ]  # type: List[ast.ClassDef]

    # region Check that test cases follow the expected order
    expected_test_case_names = [
        f"Test_{target.value.lower()}" for target in targets_with_tests
    ]
    expected_test_case_name_set = set(expected_test_case_names)

    test_case_nodes = [
        node for node in class_nodes if node.name in expected_test_case_name_set
    ]

    actual_test_case_names = [node.name for node in test_case_nodes]

    if actual_test_case_names != expected_test_case_names:
        raise AssertionError(
            f"Test case classes are either missing or not in the expected order. "
            f"Expected: {expected_test_case_names}, "
            f"but got: {actual_test_case_names}"
        )

    # endregion

    test_case_node_by_name = {node.name: node for node in test_case_nodes}

    for target in targets_with_tests:
        target_cases = cases_by_target[target]

        class_def = test_case_node_by_name[f"Test_{target.value.lower()}"]

        expected_test_method_names = []  # type: List[str]
        for case in target_cases:
            expected_or_unexpected = "expected" if case.expected else "unexpected"

            case_name_as_variable = case.name.replace("-", "_").replace(".", "_")

            expected_test_method_names.append(
                f"test_{expected_or_unexpected}_{case_name_as_variable}"
            )

        test_method_nodes = [
            node
            for node in class_def.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]

        got_test_method_names = [node.name for node in test_method_nodes]

        assert expected_test_method_names == got_test_method_names, (
            f"Expected test method names in {class_def.name} "
            f"to be {expected_test_method_names}, "
            f"but got: {got_test_method_names}"
        )

        assert len(target_cases) == len(test_method_nodes)

        for case, test_method_node in zip(target_cases, test_method_nodes):
            if len(test_method_node.body) != 1:
                raise AssertionError(
                    f"Expected a single statement (calling the _run_*_test) "
                    f"in {class_def.name}.{test_method_node.name}, "
                    f"but got {len(test_method_node.body)}"
                )

            assert isinstance(test_method_node.body[0], ast.Expr)
            statement = test_method_node.body[0].value

            if (
                not isinstance(statement, ast.Call)
                or not isinstance(statement.func, ast.Attribute)
                or not isinstance(statement.func.value, ast.Name)
                or statement.func.value.id != "self"
            ):
                raise AssertionError(
                    f"Expected the statement "
                    f"in {class_def.name}.{test_method_node.name} "
                    f"to be a call to self._run_*_test, "
                    f"but got: {ast.get_source_segment(source, statement)}\n"
                    f"AST dump: {ast.dump(statement)}"
                )

            expected_method_name = (
                "_run_expected_test" if case.expected else "_run_unexpected_test"
            )
            if statement.func.attr != expected_method_name:
                raise AssertionError(
                    f"Expected the statement "
                    f"in {class_def.name}.{test_method_node.name} "
                    f"to be a call to self.{expected_method_name}, "
                    f"but got: {ast.get_source_segment(source, statement)}"
                )

            if (
                len(statement.keywords) != 2
                or statement.keywords[0].arg != "target"
                or statement.keywords[1].arg != "case_name"
            ):
                raise AssertionError(
                    f"Expected the statement "
                    f"in {class_def.name}.{test_method_node.name} "
                    f"to be a call to self._run_*_test "
                    f"with keyword arguments target and case_name, "
                    f"but got: {ast.get_source_segment(source, statement)}\n"
                    f"AST dump: {ast.dump(statement)}"
                )

            target_source = ast.get_source_segment(source, statement.keywords[0].value)
            expected_target_source = f"aas_core_codegen.main.Target.{target.name}"

            if target_source != expected_target_source:
                raise AssertionError(
                    f"Expected the statement "
                    f"in {class_def.name}.{test_method_node.name} "
                    f"to be a call to self._run_*_test "
                    f"with keyword argument target set to {expected_target_source}, "
                    f"but got: {target_source}"
                )

            case_name_node = statement.keywords[1].value
            if (
                not isinstance(case_name_node, ast.Constant)
                or case_name_node.value != case.name
            ):
                raise AssertionError(
                    f"Expected the statement "
                    f"in {class_def.name}.{test_method_node.name} "
                    f"to be a call to self._run_*_test "
                    f"with keyword argument case_name set to {case.name!r}, "
                    f"but got: {ast.get_source_segment(source, case_name_node)}\n"
                    f"AST dump: {ast.dump(case_name_node)}"
                )


_assert_all_targets_covered()

if __name__ == "__main__":
    unittest.main()
