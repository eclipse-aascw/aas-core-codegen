"""Run an integration test on the C++ generated code."""

import argparse
import contextlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Pattern

from aas_core_codegen.common import Stripped
from live_tests import common as live_tests_common


def _cmake_project_name(namespace: Stripped) -> Stripped:
    """
    Generate the project name out of the namespace.

    >>> _cmake_project_name(Stripped('aas_core::aas_3_1'))
    'aas_core_aas_3_1'
    """
    namespace_parts = namespace.split("::")
    return Stripped("_".join([part.lower() for part in namespace_parts]))


def _cmake_variable_prefix(namespace: Stripped) -> Stripped:
    """
    Generate the prefix for all the variables in the CMake out of the namespace.

    >>> _cmake_variable_prefix(Stripped('aas_core::aas_3_1'))
    'AAS_CORE_AAS_3_1'
    """
    namespace_parts = namespace.split("::")
    return Stripped("_".join([part.upper() for part in namespace_parts]))


def _cmake_target_prefix(namespace: Stripped) -> Stripped:
    """
    Generate the prefix for all the targets in the CMake out of the namespace.

    >>> _cmake_target_prefix(Stripped('aas_core::aas_3_1'))
    'aas_core_aas_3_1'
    """
    namespace_parts = namespace.split("::")
    return Stripped("_".join([part.lower() for part in namespace_parts]))


def _generate_cmake_lists(namespace: Stripped, uses_xml_rpc: bool) -> Stripped:
    project_name = _cmake_project_name(namespace)
    variable_prefix = _cmake_variable_prefix(namespace)
    target_prefix = _cmake_target_prefix(namespace)

    relative_path = "/".join(namespace.split("::"))

    xml_rpc_src_line = (
        "        ${SRC_PATH}/xml_rpc.cpp\n"
        "        ${SRC_PATH}/json_value_verification.cpp\n"
        if uses_xml_rpc
        else ""
    )

    test_xml_rpc_block = (
        f"""\

    add_executable(test_xml_rpc test/test_xml_rpc.cpp)
    target_include_directories(test_xml_rpc PRIVATE ${{CMAKE_CURRENT_SOURCE_DIR}}/src)
    target_link_libraries(test_xml_rpc {target_prefix}_static)
    add_test(
            NAME test_xml_rpc
            COMMAND $<TARGET_FILE:test_xml_rpc>
    )
"""
        if uses_xml_rpc
        else ""
    )

    # pylint: disable=line-too-long
    return Stripped(
        f"""\
cmake_minimum_required(VERSION 3.19)
project({project_name})

set({variable_prefix}_VERSION_MAJOR 0 CACHE STRING "major version" FORCE)
set({variable_prefix}_VERSION_MINOR 0 CACHE STRING "minor version" FORCE)
set({variable_prefix}_VERSION_PATCH 1 CACHE STRING "patch version" FORCE)
set({variable_prefix}_VERSION_SUFFIX alpha.1 CACHE STRING "patch version" FORCE)

if (NOT "${{{variable_prefix}_VERSION_SUFFIX}}" STREQUAL "")
    set({variable_prefix}_VERSION
            ${{{variable_prefix}_VERSION_MAJOR}}.${{{variable_prefix}_VERSION_MINOR}}.${{{variable_prefix}_VERSION_PATCH}}-${{{variable_prefix}_VERSION_SUFFIX}}
            CACHE STRING "version" FORCE
            )
else ()
    set({variable_prefix}_VERSION
            ${{{variable_prefix}_VERSION_MAJOR}}.${{{variable_prefix}_VERSION_MINOR}}.${{{variable_prefix}_VERSION_PATCH}}
            CACHE STRING "version" FORCE
            )
endif ()

set(PROJECT_VERSION ${{{variable_prefix}_VERSION}})

OPTION(BUILD_TESTS "Build tests for {project_name}" FALSE)

if (${{BUILD_TESTS}})
    # NOTE (mristin):
    # We need to use C++17 for the <filesystem> in tests.
    set(CMAKE_CXX_STANDARD 17)
else ()
    set(CMAKE_CXX_STANDARD 11)
endif ()

# NOTE (mristin):
# See: https://crascit.com/2015/03/28/enabling-cxx11-in-cmake/
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(nlohmann_json 3 CONFIG REQUIRED)
find_package(expat 2 CONFIG REQUIRED)
find_package(tl-optional 1 CONFIG REQUIRED)
find_package(tl-expected 1 CONFIG REQUIRED)

# NOTE (mristin):
# Since there is a lot of source code, we have to compile to large object files
# with MSVC; otherwise the error C1128 is raised.
# See: https://learn.microsoft.com/en-us/cpp/error-messages/compiler-errors-1/fatal-error-c1128
IF (MSVC)
    add_compile_options(/bigobj)
ENDIF ()

if (MSVC)
    add_compile_options(/W4 /WX)
else ()
    add_compile_options(
            -Wall
            -Wextra
            -Wpedantic
            -Wno-unknown-pragmas
            -Wno-unused-parameter
            -Wno-implicit-fallthrough
            -Wno-switch
    )
endif ()


# NOTE (mristin):
# We take the following tutorial as inspiration:
# https://www.foonathan.net/2016/03/cmake-install/

SET(HEADER_PATH "${{CMAKE_CURRENT_SOURCE_DIR}}/include/{relative_path}")
SET(HEADER
        ${{HEADER_PATH}}/common.hpp
        ${{HEADER_PATH}}/constants.hpp
        ${{HEADER_PATH}}/enhancing.hpp
        ${{HEADER_PATH}}/iteration.hpp
        ${{HEADER_PATH}}/jsonization.hpp
        ${{HEADER_PATH}}/pattern.hpp
        ${{HEADER_PATH}}/revm.hpp
        ${{HEADER_PATH}}/stringification.hpp
        ${{HEADER_PATH}}/types.hpp
        ${{HEADER_PATH}}/verification.hpp
        ${{HEADER_PATH}}/visitation.hpp
        ${{HEADER_PATH}}/wstringification.hpp
        ${{HEADER_PATH}}/xmlization.hpp
        )

SET(SRC_PATH "${{CMAKE_CURRENT_SOURCE_DIR}}/src")
SET(SRC
        ${{SRC_PATH}}/common.cpp
        ${{SRC_PATH}}/constants.cpp
        ${{SRC_PATH}}/iteration.cpp
        ${{SRC_PATH}}/jsonization.cpp
        ${{SRC_PATH}}/pattern.cpp
        ${{SRC_PATH}}/revm.cpp
        ${{SRC_PATH}}/stringification.cpp
        ${{SRC_PATH}}/types.cpp
        ${{SRC_PATH}}/verification.cpp
        ${{SRC_PATH}}/visitation.cpp
        ${{SRC_PATH}}/wstringification.cpp
        ${{SRC_PATH}}/xml_common.cpp
{xml_rpc_src_line}        ${{SRC_PATH}}/xmlization.cpp
        )

# NOTE (mristin)
# MSVC does not automatically build .lib for DLLs.
# See: https://stackoverflow.com/questions/64088046/missing-lib-file-when-creating-shared-library-with-cmake-and-visual-studio-2019
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

add_library({target_prefix}_static STATIC ${{HEADER}} ${{SRC}})
set_target_properties({target_prefix}_static
        PROPERTIES
        PUBLIC_HEADER "${{HEADER}}"
        )
# NOTE (mristin):
# We need to distinguish between BUILD and INSTALL interface,
# see: https://stackoverflow.com/questions/25676277/cmake-target-include-directories-prints-an-error-when-i-try-to-add-the-source
target_include_directories({target_prefix}_static
        PUBLIC
        $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}/include>
        $<INSTALL_INTERFACE:include>
        )
target_link_libraries({target_prefix}_static
        PRIVATE
        expat::expat
        PUBLIC
        nlohmann_json::nlohmann_json
        tl::optional
        tl::expected
        )

add_library({target_prefix} SHARED ${{HEADER}} ${{SRC}})

# NOTE (mristin):
# We need to distinguish between BUILD and INSTALL interface,
# see: https://stackoverflow.com/questions/25676277/cmake-target-include-directories-prints-an-error-when-i-try-to-add-the-source
target_include_directories({target_prefix}
        PUBLIC
        $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}/include>
        $<INSTALL_INTERFACE:include>
        )
set_target_properties({target_prefix}
        PROPERTIES
        PUBLIC_HEADER "${{HEADER}}"
        )
target_link_libraries({target_prefix}
        PRIVATE
        expat::expat
        PUBLIC
        nlohmann_json::nlohmann_json
        tl::optional
        tl::expected
        )

# Testing
OPTION(BUILD_TESTS "Build tests for {project_name}" FALSE)

if (${{BUILD_TESTS}})
    # NOTE (mristin):
    # We need to use C++17 for the <filesystem>.
    set(CMAKE_CXX_STANDARD 17)

    include(CTest)
    enable_testing()

    include_directories(${{CMAKE_CURRENT_SOURCE_DIR}}/test-external)

    # region Common in test
    add_library(common_in_test test/common.hpp test/common.cpp)
    target_link_libraries(common_in_test {target_prefix}_static)

    add_library(common_jsonization_in_test
            test/common_jsonization.cpp
            test/common_jsonization.hpp
            )
    target_link_libraries(common_jsonization_in_test {target_prefix}_static)

    add_library(common_xmlization_in_test
            test/common_xmlization.cpp
            test/common_xmlization.hpp
            )
    target_link_libraries(common_xmlization_in_test {target_prefix}_static)

    add_library(common_examples_in_test
            test/common_examples.hpp
            test/common_examples.cpp
            )
    target_link_libraries(common_examples_in_test
            common_in_test
            common_xmlization_in_test
            )
    # endregion Common in test

    add_executable(test_revm test/test_revm.cpp)
    target_link_libraries(test_revm {target_prefix}_static)
    add_test(
            NAME test_revm
            COMMAND $<TARGET_FILE:test_revm>
    )

    # region Stringification
    add_executable(
            test_stringification_base64
            test/test_stringification_base64.cpp
    )
    target_link_libraries(test_stringification_base64 {target_prefix}_static)
    add_test(
            NAME test_stringification_base64
            COMMAND $<TARGET_FILE:test_stringification_base64>
    )

    add_executable(
            test_stringification_of_enums
            test/test_stringification_of_enums.cpp
    )
    target_link_libraries(test_stringification_of_enums {target_prefix}_static)
    add_test(
            NAME test_stringification_of_enums
            COMMAND $<TARGET_FILE:test_stringification_of_enums>
    )
    # endregion Stringification

    # region Wstringification
    add_executable(
            test_wstringification_of_enums
            test/test_wstringification_of_enums.cpp
    )
    target_link_libraries(test_wstringification_of_enums {target_prefix}_static)
    add_test(
            NAME test_wstringification_of_enums
            COMMAND $<TARGET_FILE:test_wstringification_of_enums>
    )
    # endregion Wstringification

    # region Jsonization
    add_executable(
            test_jsonization_of_concrete_classes
            test/test_jsonization_of_concrete_classes.cpp
    )
    target_link_libraries(
            test_jsonization_of_concrete_classes
            {target_prefix}_static
            common_in_test
            common_jsonization_in_test
    )
    add_test(
            NAME test_jsonization_of_concrete_classes
            COMMAND $<TARGET_FILE:test_jsonization_of_concrete_classes>
    )

    add_executable(
            test_jsonization_dispatch
            test/test_jsonization_dispatch.cpp
    )
    target_link_libraries(
            test_jsonization_dispatch
            {target_prefix}_static
            common_examples_in_test
            common_jsonization_in_test
    )
    add_test(
            NAME test_jsonization_dispatch
            COMMAND $<TARGET_FILE:test_jsonization_dispatch>
    )

    # endregion

    # region Xmlization
    add_executable(
            test_xmlization_of_concrete_classes
            test/test_xmlization_of_concrete_classes.cpp
    )
    target_link_libraries(
            test_xmlization_of_concrete_classes
            {target_prefix}_static
            common_in_test
            common_xmlization_in_test
    )
    add_test(
            NAME test_xmlization_of_concrete_classes
            COMMAND $<TARGET_FILE:test_xmlization_of_concrete_classes>
    )

    add_executable(
            test_xmlization_dispatch
            test/test_xmlization_dispatch.cpp
    )
    target_link_libraries(
            test_xmlization_dispatch
            {target_prefix}_static
            common_in_test
            common_examples_in_test
    )
    add_test(
            NAME test_xmlization_dispatch
            COMMAND $<TARGET_FILE:test_xmlization_dispatch>
    )

    # endregion

    # region Verification
    add_executable(
            test_verification
            test/test_verification.cpp
    )
    target_link_libraries(
            test_verification
            {target_prefix}_static
            common_in_test
            common_xmlization_in_test
    )
    add_test(
            NAME test_verification
            COMMAND $<TARGET_FILE:test_verification>
    )

    # endregion

    # region Descent and DescentOnce
    add_executable(
            test_descent_and_descent_once
            test/test_descent_and_descent_once.cpp
    )
    target_link_libraries(
            test_descent_and_descent_once
            {target_prefix}_static
            common_in_test
            common_examples_in_test
            common_xmlization_in_test
    )
    add_test(
            NAME test_descent_and_descent_once
            COMMAND $<TARGET_FILE:test_descent_and_descent_once>
    )
    # endregion

    # region XxxOrDefault
    add_executable(
            test_x_or_default
            test/test_x_or_default.cpp
    )
    target_link_libraries(
            test_x_or_default
            {target_prefix}_static
            common_in_test
            common_examples_in_test
    )
    add_test(
            NAME test_x_or_default
            COMMAND $<TARGET_FILE:test_x_or_default>
    )
    # endregion
{test_xml_rpc_block}endif ()"""
    )


def _generate_vcpkg_json(namespace: Stripped) -> Stripped:
    project_name = "-".join(
        part.replace("_", "-").lower() for part in namespace.split("::")
    )

    return Stripped(
        f"""\
{{
  "name": {json.dumps(project_name)},
  "version": "0.0.1-alpha.1",
  "dependencies": [
    {{
      "name": "vcpkg-cmake",
      "host": true
    }},
    {{
      "name": "vcpkg-cmake-config",
      "host": true
    }},
    {{
      "name": "nlohmann-json",
      "version>=": "3.11.3"
    }},
    {{
      "name": "expat",
      "version>=": "2.5.0"
    }},
    {{
      "name": "tl-optional",
      "version>=": "2021-05-02"
    }},
    {{
      "name": "tl-expected",
      "version>=": "1.1.0"
    }}
  ],
  "builtin-baseline": "91b17dd72add5718332e9a2bf55497e2b126b0a0"
}}"""
    )


def _environment_variable_prefix(namespace: Stripped) -> Stripped:
    """
    Generate the prefix for the environment variables.

    >>> _environment_variable_prefix(Stripped("aas_core::aas_3_1"))
    'AAS_CORE_AAS_3_1'
    """
    return Stripped("_".join(part.upper() for part in namespace.split("::")))


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output_dir",
        help=(
            "Path to where all the assembled project data including the test data "
            "should be copied to. If not specified, everything will be put into "
            "a temporary directory and deleted after the test."
        ),
    )
    parser.add_argument(
        "--select",
        help="Run only the test cases which match the regular expression",
        type=str,
    )
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir) if args.output_dir is not None else None

    select_text = str(args.select) if args.select is not None else None

    select: Optional[Pattern[str]] = None
    if select_text is not None:
        try:
            select = re.compile(select_text)
        except Exception as exception:
            print(f"Problems with --select {select_text}: {exception}", file=sys.stderr)
            return 1

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_cpp_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "cpp" / "expected"
    )

    assert main_cpp_expected_dir.exists() and main_cpp_expected_dir.is_dir()

    live_tests_cpp_dir = repo_root / "dev" / "test_data" / "live_tests" / "cpp"
    assert (
        live_tests_cpp_dir.exists() and live_tests_cpp_dir.is_dir()
    ), live_tests_cpp_dir

    vcpkg_root_var = os.environ.get("VCPKG_ROOT", None)
    if vcpkg_root_var is None:
        print(
            "The environment variable VCPKG_ROOT pointing "
            "to the VCPKG directory has not been set.",
            file=sys.stderr,
        )
        return 1

    vcpkg_root = pathlib.Path(vcpkg_root_var) if vcpkg_root_var is not None else None

    if not vcpkg_root.exists():
        print(
            f"The VCPKG directory pointed to by the environment variable "
            f"VCPKG_ROOT does not exist: {vcpkg_root}",
            file=sys.stderr,
        )
        return 1

    vcpkg_cmake = vcpkg_root / "scripts/buildsystems/vcpkg.cmake"
    if not vcpkg_cmake.exists():
        print(
            f"The vcpkg.cmake file does not exist: {vcpkg_cmake}. "
            f"Is your VCPKG properly set up?",
            file=sys.stderr,
        )
        return 1

    with contextlib.ExitStack() as exit_stack:
        # pylint: disable=consider-using-with

        if output_dir is None:
            temp_dir = tempfile.TemporaryDirectory()
            exit_stack.push(temp_dir)
            output_dir = pathlib.Path(temp_dir.name)
        else:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exception:
                print(
                    f"Problems with --output_dir {output_dir}: {exception}",
                    file=sys.stderr,
                )
                return 1

        for case_dir in sorted(
            path for path in main_cpp_expected_dir.iterdir() if path.is_dir()
        ):
            if select is not None and select.match(case_dir.name) is None:
                print(f"Skipping {case_dir.name} since not selected.")
                continue

            print(f"Running the live test on {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            project_dir.mkdir(exist_ok=True)

            namespace = Stripped(
                (case_dir / "input" / "snippets" / "namespace.txt")
                .read_text(encoding="utf-8")
                .strip()
            )

            print(f"Generating CMakeLists.txt in {project_dir} ...")

            # NOTE (mristin):
            # ``xml_rpc`` (and its isolated unit test) is only generated for
            # a meta-model which actually uses a JSON-able type -- we check
            # what the generator actually wrote instead of re-deriving that
            # fact here, so this can never drift out of sync with it.
            uses_xml_rpc = (
                case_dir / "expected_output" / "src" / "xml_rpc.hpp"
            ).exists()

            cmake_lists_text = _generate_cmake_lists(
                namespace=namespace, uses_xml_rpc=uses_xml_rpc
            )
            (project_dir / "CMakeLists.txt").write_text(
                cmake_lists_text, encoding="utf-8"
            )

            print(f"Generating vcpkg.json in {project_dir} ...")
            vcpkg_json_text = _generate_vcpkg_json(namespace=namespace)
            (project_dir / "vcpkg.json").write_text(vcpkg_json_text, encoding="utf-8")

            expected_output_dir = case_dir / "expected_output"

            print(
                f"Copying all the files from {expected_output_dir} to {project_dir} ..."
            )
            for path in sorted(
                path
                for path in expected_output_dir.glob("**/*")
                if path.name != "stdout.txt" and path.is_file()
            ):
                target_path = project_dir / (path.relative_to(expected_output_dir))

                # NOTE (mristin):
                # We check whether there is a change to avoid unnecessary recompilations
                # due to modification timestamps of the files.

                if not target_path.exists() or target_path.read_text(
                    encoding="utf-8"
                ) != path.read_text(encoding="utf-8"):
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(path, target_path)

            print(f"Copying Catch2 from {live_tests_cpp_dir}/boilerplate ...")

            catch_hpp_path = project_dir / "test-external" / "catch2" / "catch.hpp"
            catch_hpp_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(live_tests_cpp_dir / "boilerplate/catch.hpp", catch_hpp_path)

            cmd = [
                "cmake",
                "-DBUILD_TESTS=ON",
                "-DCMAKE_BUILD_TYPE=Debug",
                f"-DCMAKE_TOOLCHAIN_FILE={vcpkg_cmake}",
                "-S.",
                "-Bbuild",
            ]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"from {project_dir} ..."
            )
            subprocess.check_call(cmd, cwd=project_dir)

            cmd = ["cmake", "--build", "build", "-j", "8"]
            print(
                f"Running {live_tests_common.escape_and_join_command(cmd)} "
                f"from {project_dir} ..."
            )
            subprocess.check_call(cmd, cwd=project_dir)

            case_test_data_dir = live_tests_cpp_dir / "test_data" / case_dir.name

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

                env_var_prefix = _environment_variable_prefix(namespace)

                cmd = ["ctest", "-C", "DEBUG", "--output-on-failure"]
                env = os.environ.copy()

                env_var_test_data_dir = f"{env_var_prefix}_TEST_DATA_DIR"
                env_var_test_record_mode = f"{env_var_prefix}_TEST_RECORD_MODE"

                env[env_var_test_data_dir] = str(project_dir / "test_data")
                env[env_var_test_record_mode] = "1"

                build_dir = project_dir / "build"

                print(
                    f"Running "
                    f"{env_var_test_data_dir}"
                    f"={env.get(env_var_test_data_dir)} "
                    f"{env_var_test_record_mode}"
                    f"={env.get(env_var_test_record_mode)} "
                    f"{live_tests_common.escape_and_join_command(cmd)} "
                    f"from {build_dir}"
                )
                subprocess.check_call(cmd, cwd=build_dir, env=env)

    return 0


if __name__ == "__main__":
    sys.exit(main())
