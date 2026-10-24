"""Run an integration test on the C++ generated code."""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Final, Optional, Pattern

from aas_core_codegen.common import Stripped
from live_tests import common as live_tests_common

_LIVE_TESTS_CPP_DIR: Final[pathlib.Path] = (
    pathlib.Path(os.path.realpath(__file__)).parent.parent
    / "test_data"
    / "live_tests"
    / "cpp"
)


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


def _generate_cmake_lists(
    namespace: Stripped,
    uses_xml_rpc: bool,
    uses_variant: bool,
    uses_string_helpers: bool,
    uses_arithmetic: bool,
    uses_parse_int: bool,
    uses_assignment_targets: bool,
) -> Stripped:
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
    target_link_libraries(test_xml_rpc {target_prefix}_static catch_main)
    add_test(
            NAME test_xml_rpc
            COMMAND $<TARGET_FILE:test_xml_rpc>
    )

    add_executable(test_json_value_verification test/test_json_value_verification.cpp)
    target_include_directories(test_json_value_verification PRIVATE ${{CMAKE_CURRENT_SOURCE_DIR}}/src)
    target_link_libraries(test_json_value_verification {target_prefix}_static catch_main)
    add_test(
            NAME test_json_value_verification
            COMMAND $<TARGET_FILE:test_json_value_verification>
    )
"""
        if uses_xml_rpc
        else ""
    )

    test_string_helpers_block = (
        f"""\

    add_executable(test_string_helpers test/test_string_helpers.cpp)
    target_link_libraries(test_string_helpers {target_prefix}_static catch_main)
    add_test(
            NAME test_string_helpers
            COMMAND $<TARGET_FILE:test_string_helpers>
    )
"""
        if uses_string_helpers
        else ""
    )

    test_arithmetic_block = (
        f"""\

    add_executable(test_arithmetic test/test_arithmetic.cpp)
    target_link_libraries(test_arithmetic {target_prefix}_static catch_main)
    add_test(
            NAME test_arithmetic
            COMMAND $<TARGET_FILE:test_arithmetic>
    )
"""
        if uses_arithmetic
        else ""
    )

    test_parse_int_block = (
        f"""\

    add_executable(test_parse_int test/test_parse_int.cpp)
    target_link_libraries(test_parse_int {target_prefix}_static catch_main)
    add_test(
            NAME test_parse_int
            COMMAND $<TARGET_FILE:test_parse_int>
    )
"""
        if uses_parse_int
        else ""
    )

    test_assignment_targets_block = (
        f"""\

    add_executable(test_assignment_targets test/test_assignment_targets.cpp)
    target_link_libraries(test_assignment_targets {target_prefix}_static catch_main)
    add_test(
            NAME test_assignment_targets
            COMMAND $<TARGET_FILE:test_assignment_targets>
    )
"""
        if uses_assignment_targets
        else ""
    )

    find_variant_line = (
        "find_package(mpark_variant 1 CONFIG REQUIRED)\n" if uses_variant else ""
    )

    variant_link_line = "        mpark_variant\n" if uses_variant else ""

    variant_link_line_in_tests = "            mpark_variant\n" if uses_variant else ""

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
{find_variant_line}
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
        ${{HEADER_PATH}}/xml_path.hpp
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
        ${{SRC_PATH}}/xml_path.cpp
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
{variant_link_line}        )

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
{variant_link_line}        )

# Testing
OPTION(BUILD_TESTS "Build tests for {project_name}" FALSE)

if (${{BUILD_TESTS}})
    # NOTE (mristin):
    # We need to use C++17 for the <filesystem>.
    set(CMAKE_CXX_STANDARD 17)

    include(CTest)
    enable_testing()

    # NOTE (mristin):
    # The tests link only against the static library, so we do not build
    # the shared library by default to speed up the build.
    set_target_properties({target_prefix} PROPERTIES EXCLUDE_FROM_ALL ON)

    # region C++11 compatibility check
    # NOTE (mristin):
    # The library must compile as C++11, but the tests need C++17 for
    # the <filesystem>. We can not link the tests against the library compiled
    # as C++11, since common.hpp picks the standard structures (such as
    # std::optional) or their polyfills (such as tl::optional) depending on
    # the standard of whoever includes it, so the tests and the library would
    # disagree on the types. Instead, we compile the library once more as C++11
    # in this dedicated target. Nothing links against it, and no test runs it,
    # but any construct beyond C++11 breaks the build.
    #
    # We exclude this target from the default build to speed it up. The fast
    # check compiles it with ``-fsyntax-only`` from the exported compile
    # commands, which suffices to catch the constructs beyond C++11.
    add_library({target_prefix}_cpp11_compatibility_check OBJECT ${{HEADER}} ${{SRC}})
    set_target_properties({target_prefix}_cpp11_compatibility_check
            PROPERTIES
            EXCLUDE_FROM_ALL ON
            CXX_STANDARD 11
            CXX_STANDARD_REQUIRED ON
            CXX_EXTENSIONS OFF
            )
    target_include_directories({target_prefix}_cpp11_compatibility_check
            PRIVATE
            ${{CMAKE_CURRENT_SOURCE_DIR}}/include
            )
    target_link_libraries({target_prefix}_cpp11_compatibility_check
            PRIVATE
            expat::expat
            nlohmann_json::nlohmann_json
            tl::optional
            tl::expected
{variant_link_line_in_tests}            )
    # endregion C++11 compatibility check

    include_directories(${{CMAKE_CURRENT_SOURCE_DIR}}/test-external)

    # region Common in test
    # NOTE (mristin):
    # Compiling the implementation of Catch2 takes long, so we compile it only
    # once and link it into all the tests.
    add_library(catch_main OBJECT test/catch_main.cpp)

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
    target_link_libraries(test_revm {target_prefix}_static catch_main)
    add_test(
            NAME test_revm
            COMMAND $<TARGET_FILE:test_revm>
    )

    # region Stringification
    add_executable(
            test_stringification_base64
            test/test_stringification_base64.cpp
    )
    target_link_libraries(test_stringification_base64 {target_prefix}_static catch_main)
    add_test(
            NAME test_stringification_base64
            COMMAND $<TARGET_FILE:test_stringification_base64>
    )

    add_executable(
            test_stringification_of_enums
            test/test_stringification_of_enums.cpp
    )
    target_link_libraries(test_stringification_of_enums {target_prefix}_static catch_main)
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
    target_link_libraries(test_wstringification_of_enums {target_prefix}_static catch_main)
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
            catch_main
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
            catch_main
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
            catch_main
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
            catch_main
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
            catch_main
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
            catch_main
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
            catch_main
            common_in_test
            common_examples_in_test
    )
    add_test(
            NAME test_x_or_default
            COMMAND $<TARGET_FILE:test_x_or_default>
    )
    # endregion
{test_xml_rpc_block}{test_string_helpers_block}{test_arithmetic_block}{test_parse_int_block}\
{test_assignment_targets_block}endif ()"""
    )


def _generate_vcpkg_json(namespace: Stripped, uses_variant: bool) -> Stripped:
    project_name = "-".join(
        part.replace("_", "-").lower() for part in namespace.split("::")
    )

    # NOTE (mristin):
    # We can not constrain the version of mpark-variant, since the baseline
    # records it with a scheme which vcpkg can not compare against ``version>=``.
    # The baseline pins it to 1.4.0 anyway.
    variant_dependency = ',\n    "mpark-variant"' if uses_variant else ""

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
    }}{variant_dependency}
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


def prepare_project(
    case_dir: pathlib.Path, project_dir: pathlib.Path, vcpkg_cmake: pathlib.Path
) -> Stripped:
    """
    Copy the generated code of the case to ``project_dir`` and configure it.

    The build is configured in ``project_dir / "build"``, and we also export
    the compile commands so that the fast check can compile without building.
    Return the namespace of the generated code.
    """
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
    uses_xml_rpc = (case_dir / "expected_output" / "src" / "xml_rpc.hpp").exists()

    # NOTE (mristin):
    # Likewise, we check whether the generator relies on a variant
    # (only for the named unions) in what it actually wrote.
    common_hpp_path = (
        case_dir
        / "expected_output"
        / "include"
        / namespace.replace("::", "/")
        / "common.hpp"
    )
    uses_variant = "mpark/variant.hpp" in common_hpp_path.read_text(encoding="utf-8")

    # NOTE (mristin):
    # Likewise, the tests of the string helpers are only generated for
    # a meta-model which slices strings or calls ``find``.
    uses_string_helpers = (
        case_dir / "expected_output" / "test" / "test_string_helpers.cpp"
    ).exists()

    # Likewise, the unit test of the arithmetic operations is only
    # generated if the meta-model uses the modulo or ``abs``.
    uses_arithmetic = (
        case_dir / "expected_output" / "test" / "test_arithmetic.cpp"
    ).exists()

    # Likewise, the unit test of ``int`` is only generated if the meta-model uses
    # it.
    uses_parse_int = (
        case_dir / "expected_output" / "test" / "test_parse_int.cpp"
    ).exists()

    # Likewise, the unit test of the assignments to the properties and the list
    # items is only generated for the meta-model which defines the corresponding
    # verification functions.
    #
    # NOTE (mristin):
    # Only C++ executes these assignments in the unit tests, as it copies
    # the vectors by value, unlike Python and the other targets,
    # see :py:mod:`aas_core_codegen.cpp.tests._generate_test_assignment_targets`.
    uses_assignment_targets = (
        case_dir / "expected_output" / "test" / "test_assignment_targets.cpp"
    ).exists()

    cmake_lists_text = _generate_cmake_lists(
        namespace=namespace,
        uses_xml_rpc=uses_xml_rpc,
        uses_variant=uses_variant,
        uses_string_helpers=uses_string_helpers,
        uses_arithmetic=uses_arithmetic,
        uses_parse_int=uses_parse_int,
        uses_assignment_targets=uses_assignment_targets,
    )
    (project_dir / "CMakeLists.txt").write_text(cmake_lists_text, encoding="utf-8")

    print(f"Generating vcpkg.json in {project_dir} ...")
    vcpkg_json_text = _generate_vcpkg_json(
        namespace=namespace, uses_variant=uses_variant
    )
    (project_dir / "vcpkg.json").write_text(vcpkg_json_text, encoding="utf-8")

    expected_output_dir = case_dir / "expected_output"

    live_tests_common.copy_expected_output(expected_output_dir, project_dir)

    print(f"Copying Catch2 from {_LIVE_TESTS_CPP_DIR}/boilerplate ...")

    catch_hpp_path = project_dir / "test-external" / "catch2" / "catch.hpp"
    catch_hpp_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_LIVE_TESTS_CPP_DIR / "boilerplate/catch.hpp", catch_hpp_path)

    cmd = [
        "cmake",
        "-DBUILD_TESTS=ON",
        "-DCMAKE_BUILD_TYPE=Debug",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DCMAKE_TOOLCHAIN_FILE={vcpkg_cmake}",
        "-S.",
        "-Bbuild",
    ]

    # NOTE (mristin):
    # The live tests re-compile the same generated code over and over again,
    # so we cache the compilation if ccache is available.
    if shutil.which("ccache") is not None:
        cmd.append("-DCMAKE_CXX_COMPILER_LAUNCHER=ccache")

    print(
        f"Running {live_tests_common.escape_and_join_command(cmd)} "
        f"from {project_dir} ..."
    )
    subprocess.check_call(cmd, cwd=project_dir)

    return namespace


def find_vcpkg_cmake() -> Optional[pathlib.Path]:
    """
    Find the CMake toolchain file of vcpkg based on ``VCPKG_ROOT``.

    Report to STDERR and return ``None`` if it could not be found.
    """
    vcpkg_root_var = os.environ.get("VCPKG_ROOT", None)
    if vcpkg_root_var is None:
        print(
            "The environment variable VCPKG_ROOT pointing "
            "to the VCPKG directory has not been set.",
            file=sys.stderr,
        )
        return None

    vcpkg_root = pathlib.Path(vcpkg_root_var)

    if not vcpkg_root.exists():
        print(
            f"The VCPKG directory pointed to by the environment variable "
            f"VCPKG_ROOT does not exist: {vcpkg_root}",
            file=sys.stderr,
        )
        return None

    vcpkg_cmake = vcpkg_root / "scripts/buildsystems/vcpkg.cmake"
    if not vcpkg_cmake.exists():
        print(
            f"The vcpkg.cmake file does not exist: {vcpkg_cmake}. "
            f"Is your VCPKG properly set up?",
            file=sys.stderr,
        )
        return None

    return vcpkg_cmake


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    parser.add_argument(
        "--jobs",
        help="Number of the parallel jobs to build the C++ code",
        type=int,
        default=8,
    )
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_cpp_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "cpp" / "expected"
    )

    assert main_cpp_expected_dir.exists() and main_cpp_expected_dir.is_dir()

    assert (
        _LIVE_TESTS_CPP_DIR.exists() and _LIVE_TESTS_CPP_DIR.is_dir()
    ), _LIVE_TESTS_CPP_DIR

    vcpkg_cmake = find_vcpkg_cmake()
    if vcpkg_cmake is None:
        return 1

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        for case_dir in live_tests_common.select_case_dirs(
            main_cpp_expected_dir, select
        ):
            print(f"Running the live test on {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            namespace = prepare_project(case_dir, project_dir, vcpkg_cmake)

            cmd = ["cmake", "--build", "build", "-j", str(args.jobs)]

            # NOTE (mristin):
            # We make ccache ignore the absolute paths of the projects so that
            # the cache is hit even if the output directory changes between
            # the runs. Without ccache, these variables have no effect.
            build_env = os.environ.copy()
            build_env["CCACHE_BASEDIR"] = str(output_dir.resolve())
            build_env["CCACHE_NOHASHDIR"] = "1"

            print(
                f"Running CCACHE_BASEDIR={build_env['CCACHE_BASEDIR']} "
                f"CCACHE_NOHASHDIR={build_env['CCACHE_NOHASHDIR']} "
                f"{live_tests_common.escape_and_join_command(cmd)} "
                f"from {project_dir} ..."
            )
            subprocess.check_call(cmd, cwd=project_dir, env=build_env)

            case_test_data_dir = _LIVE_TESTS_CPP_DIR / "test_data" / case_dir.name

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
