# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Run integration tests on the Java generated code."""

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Optional, Pattern

from aas_core_codegen.common import Stripped

from live_tests import common as live_tests_common


def prepare_project(case_dir: pathlib.Path, project_dir: pathlib.Path) -> Stripped:
    """
    Copy the generated code of the case to ``project_dir`` and set up Maven.

    Return the Java package of the generated code.
    """
    project_dir.mkdir(exist_ok=True)

    package = Stripped(
        (case_dir / "input" / "snippets" / "package.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    expected_output_dir = case_dir / "expected_output"

    live_tests_common.copy_expected_output(expected_output_dir, project_dir)

    group_id = package
    artifact_id = "-".join(package.split("."))

    (project_dir / "pom.xml").write_text(
        f"""\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 \
http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>{group_id}</groupId>
  <artifactId>{artifact_id}</artifactId>
  <version>0.0.1</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>2.17.2</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
""",
        encoding="utf-8",
    )

    return package


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    if shutil.which("mvn") is None:
        print(
            "mvn (Maven) could not be found on your PATH -- "
            "have you installed Maven?",
            file=sys.stderr,
        )
        return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_java_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "java" / "expected"
    )

    assert main_java_expected_dir.exists() and main_java_expected_dir.is_dir()

    live_tests_java_dir = repo_root / "dev" / "test_data" / "live_tests" / "java"

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_java_expected_dir, select
        ):
            print(f"Running the live test on {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            package = prepare_project(case_dir, project_dir)

            cmd = ["mvn", "--batch-mode", "test-compile"]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {project_dir}"
            )
            subprocess.check_call(cmd, cwd=project_dir)

            case_test_data_dir = live_tests_java_dir / "test_data" / case_dir.name

            if not case_test_data_dir.exists():
                # NOTE (mristin):
                # We fall back to the shared test data.
                case_test_data_dir = live_tests_common.common_test_data_dir_for_case(
                    case_name=case_dir.name
                )

            if case_test_data_dir.exists():
                # NOTE (mristin):
                # Java expects the test data in ``test_data`` relative to the working
                # directory of the JVM process, which, by default, is the base
                # directory of the Maven module (see ``Common.TEST_DATA_DIR`` in the
                # generated test code).
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

                env_var_prefix = re.sub(
                    r"(?<=[a-z])(?=[A-Z])", "_", package.replace(".", "_")
                ).upper()

                cmd = ["mvn", "--batch-mode", "test"]
                env = os.environ.copy()

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
