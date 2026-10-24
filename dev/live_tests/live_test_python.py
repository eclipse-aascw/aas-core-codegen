"""Run integration tests on the Python generated code."""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Final, Optional, Pattern, Sequence

from aas_core_codegen.common import Stripped
from live_tests import common as live_tests_common

#: Dependencies needed to check and test the generated code, as specified in
#: ``dev/pyproject.toml`` of the project
DEV_DEPENDENCIES: Final[Sequence[str]] = (
    "mypy==2.4.0",
    "pylint==2.15.4; python_version<'3.11'",
    "pylint==4.0.3; python_version>'3.10'",
)


def prepare_project(case_dir: pathlib.Path, project_dir: pathlib.Path) -> Stripped:
    """
    Copy the generated code of the case to ``project_dir`` and set up the project.

    Return the qualified name of the generated module.
    """
    project_dir.mkdir(exist_ok=True)

    qualified_module_name = Stripped(
        (case_dir / "input" / "snippets" / "qualified_module_name.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    expected_output_dir = case_dir / "expected_output"

    live_tests_common.copy_expected_output(expected_output_dir, project_dir)

    project_name = qualified_module_name.replace("_", "-")

    (project_dir / "pyproject.toml").write_text(
        f"""\
[build-system]
requires = ["setuptools", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "{project_name}"
version = "0.0.1"
requires-python = ">=3.9"

[tool.setuptools.packages.find]
include = ["{qualified_module_name}"]
exclude = ["dev"]

[tool.setuptools.package-data]
"{qualified_module_name}" = ["py.typed"]
""",
        encoding="utf-8",
    )

    dev_dependencies = ",\n".join(
        f"    {json.dumps(dependency)}" for dependency in DEV_DEPENDENCIES
    )

    (project_dir / "dev" / "pyproject.toml").write_text(
        f"""\
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{project_name}-dev"
version = "0.0.1"
requires-python = ">=3.8"

dependencies = [
{dev_dependencies}
]

[tool.setuptools]
packages = [
    "tests"
]

# NOTE (mristin):
# We put the configuration of mypy and pylint in separate files as it is a nightmare
# to configure them with pyproject.toml not living in the current working directory
# which is the repository root.
""",
        encoding="utf-8",
    )

    pylint_rc = project_dir / "dev" / "pylint.rc"

    pylint_disables = (
        "too-few-public-methods,len-as-condition,duplicate-code,no-else-raise,"
        "no-else-return,too-many-locals,too-many-branches,"
        "too-many-nested-blocks,too-many-return-statements,"
        "unsubscriptable-object,not-an-iterable,broad-except,"
        "too-many-statements,protected-access,unnecessary-pass,"
        "too-many-statements,too-many-arguments,no-member,"
        "too-many-instance-attributes,too-many-lines,undefined-variable,"
        "unnecessary-lambda,assignment-from-none,useless-return,"
        "unused-argument,too-many-boolean-expressions,"
        "consider-using-f-string,use-dict-literal,invalid-name,"
        "no-else-continue,no-else-break,unneeded-not,"
        "too-many-public-methods,line-too-long,too-many-ancestors,"
        "wrong-import-position,too-many-positional-arguments,"
        "wrong-import-order,unused-import,missing-docstring,"
        "superfluous-parens"
    )

    pylint_rc.write_text(
        f"""\
[FORMAT]
max-line-length=120

[MESSAGES CONTROL]
disable={pylint_disables}
""",
        encoding="utf-8",
    )

    (project_dir / qualified_module_name / "py.typed").write_text(
        """\
# Marker file for PEP 561. The mypy package uses inline types.
""",
        encoding="utf-8",
    )

    (project_dir / qualified_module_name / "__init__.py").write_text(
        f"# This is {qualified_module_name}!\n", encoding="utf-8"
    )

    # NOTE (mristin):
    # The tests import each other as ``tests.*``. We make them a package as in
    # the generated SDKs so that mypy can resolve these imports.
    (project_dir / "dev" / "tests" / "__init__.py").write_text(
        "# This is the package of the tests.\n", encoding="utf-8"
    )

    # NOTE (mristin):
    # The tests import each other as ``tests.*``. We make them a package as in
    # the generated SDKs so that mypy can resolve these imports.
    (project_dir / "dev" / "tests" / "__init__.py").write_text(
        "# This is the package of the tests.\n", encoding="utf-8"
    )

    return qualified_module_name


def _venv_python(venv_dir: pathlib.Path) -> pathlib.Path:
    """Determine the path to the Python interpreter of the virtual environment."""
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"

    return venv_dir / "bin" / "python"


def _site_packages(python: pathlib.Path) -> pathlib.Path:
    """Determine the directory where ``python`` installs the pure packages."""
    return pathlib.Path(
        subprocess.check_output(
            [
                str(python),
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            encoding="utf-8",
        ).strip()
    )


def prepare_venv(output_dir: pathlib.Path) -> Optional[pathlib.Path]:
    """
    Create the virtual environment shared by all the projects in ``output_dir``.

    We install only :py:data:`DEV_DEPENDENCIES` here, and never modify
    the virtual environment afterwards so that the cases can run in parallel.
    The virtual environments of the individual cases inherit its packages.
    Return the path to the Python interpreter of the virtual environment, or report
    to STDERR and return ``None``.
    """
    venv_dir = output_dir / "venv"

    if not venv_dir.exists():
        cmd = [sys.executable, "-m", "venv", str(venv_dir)]
        print(f"Running {live_tests_common.escape_and_join_command(cmd)}")
        subprocess.check_call(cmd)

    venv_python = _venv_python(venv_dir)
    if not venv_python.exists():
        print(
            f"Python could not be found in the virtual environment: {venv_python}",
            file=sys.stderr,
        )
        return None

    # NOTE (mristin):
    # The virtual environments of the cases use the pip of the shared virtual
    # environment through ``pip --python``, which is available only since pip 22.3.
    # The pip bundled with older Python versions (*e.g.*, Python 3.10) is too old,
    # so we upgrade it. Pip leaves a satisfied requirement untouched.
    for cmd in [
        [str(venv_python), "-m", "pip", "install", "--quiet", "pip>=22.3"],
        [str(venv_python), "-m", "pip", "install", "--quiet"] + list(DEV_DEPENDENCIES),
    ]:
        print(f"Running {live_tests_common.escape_and_join_command(cmd)}")
        subprocess.check_call(cmd)

    return venv_python


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_python_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "python" / "expected"
    )

    assert main_python_expected_dir.exists() and main_python_expected_dir.is_dir()

    live_tests_python_dir = repo_root / "dev" / "test_data" / "live_tests" / "python"

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        shared_venv_python = prepare_venv(output_dir)
        if shared_venv_python is None:
            return 1

        shared_site_packages = _site_packages(shared_venv_python)

        for case_dir in live_tests_common.select_case_dirs(
            main_python_expected_dir, select
        ):
            print(f"Running the live test on {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            qualified_module_name = prepare_project(case_dir, project_dir)

            # NOTE (mristin):
            # We install the package and its tests in a virtual environment of
            # the case so that the cases do not clash (*e.g.*, all of them install
            # the package ``tests``), and can run in parallel. To avoid installing
            # the dependencies for every case, the virtual environment of the case
            # inherits the packages of the shared virtual environment through
            # a ``.pth`` file. We create it without pip, and use the pip of the shared
            # virtual environment instead.
            venv_dir = project_dir / "venv"
            if not venv_dir.exists():
                cmd = [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)]
                print(f"Running {live_tests_common.escape_and_join_command(cmd)}")
                subprocess.check_call(cmd)

            venv_python = _venv_python(venv_dir)

            (_site_packages(venv_python) / "shared_venv.pth").write_text(
                f"{shared_site_packages}\n", encoding="utf-8"
            )

            for package_dir in [".", "dev/"]:
                cmd = [
                    str(shared_venv_python),
                    "-m",
                    "pip",
                    "--python",
                    str(venv_python),
                    "install",
                    "-e",
                    package_dir,
                ]
                print(
                    f"Running {live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir)

            # NOTE (mristin):
            # We type-check the tests as well since the type errors in them would
            # otherwise remain uncovered, as the generated SDKs check them, too.
            cmd = [
                str(venv_python),
                "-m",
                "mypy",
                "--strict",
                qualified_module_name,
                "dev/tests",
            ]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {project_dir}"
            )
            subprocess.check_call(cmd, cwd=project_dir)

            cmd = [
                str(venv_python),
                "-m",
                "pylint",
                "--rcfile=dev/pylint.rc",
                qualified_module_name,
            ]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {project_dir}"
            )
            subprocess.check_call(cmd, cwd=project_dir)

            case_test_data_dir = live_tests_python_dir / "test_data" / case_dir.name

            if not case_test_data_dir.exists():
                # NOTE (mristin):
                # We fall back to the shared test data.
                case_test_data_dir = live_tests_common.common_test_data_dir_for_case(
                    case_name=case_dir.name
                )

            if case_test_data_dir.exists():
                target_test_data = project_dir / "test_data"

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

                env_var_prefix = qualified_module_name.replace(".", "_").upper()

                cmd = [
                    str(venv_python),
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "dev/tests",
                ]

                env = os.environ.copy()

                # NOTE (mristin):
                # We remove PYTHONPATH from the environment, or the python in the live
                # test will run with the modules imported from *this* repository as
                # well.
                env.pop("PYTHONPATH", None)

                env_var_test_record_mode = f"{env_var_prefix}_TESTS_RECORD_MODE"
                env[env_var_test_record_mode] = "1"

                print(
                    f"Running "
                    f"{env_var_test_record_mode}"
                    f"={env.get(env_var_test_record_mode)} "
                    f"{live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir, env=env)

                # NOTE (mristin):
                # Parts of the Python tests were accessing tests.common which was not
                # properly imported. We only run mypy on the library, but not on tests,
                # so that bug remained uncovered in the live tests. We now re-run
                # the tests against the recorded traces to avoid the regression.

                env[env_var_test_record_mode] = "0"
                print(
                    f"Running the tests again without re-recording with "
                    f"{env_var_test_record_mode}"
                    f"={env.get(env_var_test_record_mode)} "
                    f"{live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir, env=env)

    return 0


if __name__ == "__main__":
    sys.exit(main())
