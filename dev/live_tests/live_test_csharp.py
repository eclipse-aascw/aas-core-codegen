# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Run integration tests on the C# generated code."""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Pattern

from aas_core_codegen.common import Stripped

from live_tests import common as live_tests_common


def prepare_solution(case_dir: pathlib.Path, solution_dir: pathlib.Path) -> Stripped:
    """
    Copy the generated code of the case to ``solution_dir`` and set up the solution.

    Return the namespace of the generated code.
    """
    solution_dir.mkdir(exist_ok=True)

    namespace = Stripped(
        (case_dir / "input" / "snippets" / "namespace.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    expected_output_dir = case_dir / "expected_output"

    live_tests_common.copy_expected_output(expected_output_dir, solution_dir)

    (solution_dir / namespace / f"{namespace}.csproj").write_text(
        """\
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <Configurations>Debug;Release;DebugSlow</Configurations>
    <Platforms>AnyCPU</Platforms>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )

    (solution_dir / f"{namespace}.Tests" / f"{namespace}.Tests.csproj").write_text(
        f"""\
<Project Sdk="Microsoft.NET.Sdk">
    <PropertyGroup>
        <TargetFramework>net10.0</TargetFramework>
        <IsPackable>false</IsPackable>
        <Configurations>Debug;Release;DebugSlow</Configurations>
        <Platforms>AnyCPU</Platforms>
        <Nullable>enable</Nullable>
        <OutputType>Library</OutputType>
    </PropertyGroup>

    <PropertyGroup Condition=" '$(Configuration)' == 'Debug' ">
      <DefineConstants>TRACECOREAPP</DefineConstants>
    </PropertyGroup>

    <ItemGroup>
        <PackageReference Include="NUnit" Version="3.13.3" />
        <PackageReference Include="NUnit3TestAdapter" Version="4.2.1" />
        <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.1.0" />
        <PackageReference Include="OpenCover" Version="4.7.1221" />
        <PackageReference Include="coverlet.msbuild" Version="3.1.2">
          <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
          <PrivateAssets>all</PrivateAssets>
        </PackageReference>
    </ItemGroup>

    <ItemGroup>
      <ProjectReference Include="../{namespace}/{namespace}.csproj" />
    </ItemGroup>

    <ItemGroup>
      <None Update="TestResources/**">
        <CopyToOutputDirectory>Always</CopyToOutputDirectory>
      </None>
    </ItemGroup>
</Project>
""",
        encoding="utf-8",
    )

    solution_name = "-".join(part.lower() for part in namespace.split("."))

    cmd = ["dotnet", "new", "sln", "-n", solution_name, "--force"]
    print(
        f"Running {live_tests_common.escape_and_join_command(cmd)} "
        f"in {solution_dir} ..."
    )
    subprocess.check_call(cmd, cwd=solution_dir)

    cmd = [
        "dotnet",
        "sln",
        f"{solution_name}.slnx",
        "add",
        f"{namespace}/{namespace}.csproj",
        f"{namespace}.Tests/{namespace}.Tests.csproj",
    ]
    print(
        f"Running {live_tests_common.escape_and_join_command(cmd)} "
        f"in {solution_dir} ..."
    )
    subprocess.check_call(cmd, cwd=solution_dir)

    return namespace


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_csharp_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "csharp" / "expected"
    )

    assert main_csharp_expected_dir.exists() and main_csharp_expected_dir.is_dir()

    live_tests_csharp_dir = repo_root / "dev" / "test_data" / "live_tests" / "csharp"

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_csharp_expected_dir, select
        ):
            print(f"Running the live test on {case_dir.name} ...")

            solution_dir = output_dir / case_dir.name
            namespace = prepare_solution(case_dir, solution_dir)

            cmd = ["dotnet", "build"]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"in {solution_dir} ..."
            )
            subprocess.check_call(cmd, cwd=solution_dir)

            case_test_data_dir = live_tests_csharp_dir / "test_data" / case_dir.name

            if not case_test_data_dir.exists():
                # NOTE (mristin):
                # We fall back to the shared test data.
                case_test_data_dir = live_tests_common.common_test_data_dir_for_case(
                    case_name=case_dir.name
                )

            if case_test_data_dir.exists():
                target_test_data = solution_dir / "test_data"
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

                env_var_prefix = "_".join(part.upper() for part in namespace.split("."))

                cmd = ["dotnet", "test"]
                env = os.environ.copy()

                env_var_test_data_dir = f"{env_var_prefix}_TESTS_TEST_DATA_DIR"
                env_var_test_record_mode = f"{env_var_prefix}_TESTS_RECORD_MODE"

                env[env_var_test_data_dir] = str(solution_dir / "test_data")
                env[env_var_test_record_mode] = "1"

                print(
                    f"Running "
                    f"{env_var_test_data_dir}"
                    f"={env.get(env_var_test_data_dir)} "
                    f"{env_var_test_record_mode}"
                    f"={env.get(env_var_test_record_mode)} "
                    f"{live_tests_common.escape_and_join_command(cmd)} "
                    f"in {solution_dir}"
                )
                subprocess.check_call(cmd, cwd=solution_dir, env=env)

    return 0


if __name__ == "__main__":
    sys.exit(main())
