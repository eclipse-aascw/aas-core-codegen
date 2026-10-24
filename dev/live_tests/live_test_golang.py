"""Run integration tests on the Golang generated code."""


import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Pattern

if sys.version_info < (3, 12):
    import more_itertools as itertools
else:
    import itertools

from aas_core_codegen.common import Stripped
from aas_core_codegen.golang import common as golang_common

from live_tests import common as live_tests_common


def find_goimports() -> Optional[str]:
    """Find the goimports executable, or report to STDERR and return ``None``."""
    # NOTE (mristin):
    # We use goimports to post-process the generated code so that we don't have to
    # fiddle around in the code generator to figure out which imports are used and
    # which can be omitted.
    #
    # Go compiler treats unused imports as errors, so removing unused imports with
    # goimports is strictly necessary.

    goimports_path = shutil.which("goimports")
    if goimports_path is not None:
        return goimports_path

    alternative_goimports_path = pathlib.Path.home() / "go/bin/goimports"
    if alternative_goimports_path.exists():
        return str(alternative_goimports_path)

    path_env_var = os.environ.get("PATH", "")
    print(
        f"goimports could not be found on your PATH "
        f"nor in {alternative_goimports_path} -- have you installed it "
        f"with go install golang.org/x/tools/cmd/goimports@latest ?\n\n"
        f"PATH: {path_env_var}",
        file=sys.stderr,
    )
    return None


def prepare_module(
    case_dir: pathlib.Path, module_dir: pathlib.Path, goimports_path: str
) -> Stripped:
    """
    Copy the generated code of the case to ``module_dir`` and set up the module.

    Return the repository URL of the module.
    """
    module_dir.mkdir(exist_ok=True)

    repo_url = Stripped(
        (case_dir / "input" / "snippets" / "repo_url.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    live_tests_common.copy_expected_output(case_dir / "expected_output", module_dir)

    (module_dir / "go.mod").write_text(
        f"""\
module {repo_url}

go 1.18
""",
        encoding="utf-8",
    )

    for chunk in itertools.batched(sorted(module_dir.glob("**/*.go")), 64):
        cmd = [goimports_path, "-w"] + [
            str(pth.relative_to(module_dir)) for pth in chunk
        ]
        print(
            f"Running {live_tests_common.escape_and_join_command(cmd)} "
            f"in {module_dir}"
        )
        subprocess.check_call(cmd, cwd=module_dir)

    return repo_url


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    goimports_path = find_goimports()
    if goimports_path is None:
        return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_golang_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "golang" / "expected"
    )

    assert main_golang_expected_dir.exists() and main_golang_expected_dir.is_dir()

    live_tests_golang_dir = repo_root / "dev" / "test_data" / "live_tests" / "golang"

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_golang_expected_dir, select
        ):
            print(f"Running the live test on {case_dir.name} ...")

            module_dir = output_dir / case_dir.name
            repo_url = prepare_module(case_dir, module_dir, goimports_path)

            cmd = ["go", "build", "./..."]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {module_dir}"
            )
            subprocess.check_call(cmd, cwd=module_dir)

            case_test_data_dir = live_tests_golang_dir / "test_data" / case_dir.name

            if not case_test_data_dir.exists():
                # NOTE (mristin):
                # We fall back to the shared test data.
                case_test_data_dir = live_tests_common.common_test_data_dir_for_case(
                    case_name=case_dir.name
                )

            if case_test_data_dir.exists():
                # NOTE (mristin):
                # Go expects the test data in ``testdata`` (no underscore) directory.
                target_test_data = module_dir / "testdata"

                print(
                    f"Copying test data from {case_test_data_dir} "
                    f"to {target_test_data} ..."
                )
                for pth in sorted(case_test_data_dir.glob("**/*")):
                    if not pth.is_file():
                        continue

                    target_pth = target_test_data / pth.relative_to(case_test_data_dir)

                    target_pth.parent.mkdir(exist_ok=True, parents=True)

                    shutil.copy(pth, target_pth)

                print("Running the tests...")

                env_var_prefix = golang_common.repo_url_to_environment_variable(
                    repo_url
                )

                cmd = ["go", "test", "./..."]
                env = os.environ.copy()

                env_var_test_data_dir = f"{env_var_prefix}_TEST_DATA_DIR"
                env_var_test_record_mode = f"{env_var_prefix}_TEST_RECORD_MODE"

                env[env_var_test_data_dir] = str(module_dir / "testdata")
                env[env_var_test_record_mode] = "1"

                print(
                    f"Running "
                    f"{env_var_test_data_dir}"
                    f"={env.get(env_var_test_data_dir)} "
                    f"{env_var_test_record_mode}"
                    f"={env.get(env_var_test_record_mode)} "
                    f"{live_tests_common.escape_and_join_command(cmd)} "
                    f"in {module_dir}"
                )
                subprocess.check_call(cmd, cwd=module_dir, env=env)

    return 0


if __name__ == "__main__":
    sys.exit(main())
