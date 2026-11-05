# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code for common functionality shared across the tests."""

import re
from typing import List

from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.java import (
    common as java_common,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


def _package_to_upper_snake(
    package: java_common.PackageIdentifier,
) -> Identifier:
    """
    Convert a snake case dotted package into UPPER_SNAKE_CASE.

    >>> _package_to_upper_snake(java_common.PackageIdentifier("aas_core.aas3_1"))
    'AAS_CORE_AAS3_1'

    >>> _package_to_upper_snake(java_common.PackageIdentifier("simple_test"))
    'SIMPLE_TEST'
    """
    result = package.replace(".", "_")

    # Insert underscore between lowercase and uppercase (aasCore → aas_Core)
    result = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", result)

    return Identifier(result.upper())


def generate(package: java_common.PackageIdentifier) -> List[java_common.JavaFile]:
    """Generate code for common functionality shared across the tests."""
    blocks = [
        Stripped(
            f"""\
public static final String RECORD_MODE_ENVIRONMENT_VARIABLE_NAME =
{I}"{_package_to_upper_snake(package)}_TESTS_RECORD_MODE";"""
        ),
        Stripped(
            f"""\
// NOTE (empwilli):
// It is tedious to record manually all the expected error messages.
// Therefore we include this variable to steer the automatic recording.
// We intentionally inter-twine the recording code with the test code
// to keep them close to each other so that they are easier to maintain.
public static final boolean RECORD_MODE =
{I}System.getenv("{_package_to_upper_snake(package)}_TESTS_RECORD_MODE") != null && (
{II}System.getenv(RECORD_MODE_ENVIRONMENT_VARIABLE_NAME).equalsIgnoreCase("true") ||
{II}System.getenv(RECORD_MODE_ENVIRONMENT_VARIABLE_NAME).equalsIgnoreCase("on") ||
{II}System.getenv(RECORD_MODE_ENVIRONMENT_VARIABLE_NAME).equalsIgnoreCase("1") ||
{II}System.getenv(RECORD_MODE_ENVIRONMENT_VARIABLE_NAME).equalsIgnoreCase("yes"));""",
        ),
        Stripped(
            f"""\
@SuppressWarnings("unchecked")
public static <T extends IClass> T mustFind(IClass container, Class<T> type) {{
{I}if (type.isInstance(container)) {{
{II}return type.cast(container);
{I}}}
{I}for (IClass current : container.descend()) {{
{II}if (type.isInstance(current)) {{
{III}return type.cast(current);
{II}}}
{I}}}
{I}throw new IllegalStateException("No instance of " + type.getSimpleName() + " could be found");
}}"""
        ),
        Stripped(
            f"""\
public static List<Path> findPaths(Path path, String fileExtension) throws IOException {{
{I}if (!Files.isDirectory(path)) {{
{II}throw new IllegalArgumentException("Path must be a directory!");
{I}}}

{I}List<Path> result;
{I}try (Stream<Path> walk = Files.walk(path)) {{
{II}result =
{III}walk.filter(p -> !Files.isDirectory(p))
{IIII}.filter(f -> f.toString().endsWith(fileExtension))
{IIII}.collect(Collectors.toList());
{I}}}
{I}return result;
}}""",
        ),
        Stripped(
            f"""\
public static List<Path> findDirs(Path path) throws IOException {{
{I}if (!Files.isDirectory(path)) {{
{II}throw new IllegalArgumentException("Path must be a directory!");
{I}}}

{I}List<Path> result;
{I}try (Stream<Path> walk = Files.walk(path)) {{
{II}result = walk.filter(p -> Files.isDirectory(p)).collect(Collectors.toList());
{I}}}
{I}return result;
}}""",
        ),
        Stripped(
            f"""\
public static <T> List<T> asList(Iterable<T> iterable) {{
{I}return StreamSupport.stream(iterable.spliterator(), false).collect(Collectors.toList());
}}"""
        ),
        Stripped(
            f"""\
public static void assertNoVerificationErrors(List<Reporting.Error> errors, Path path) {{
{I}if (!errors.isEmpty()) {{
{II}StringBuilder stringBuilder = new StringBuilder();
{II}stringBuilder
{III}.append("Expected no errors when verifying the instance de-serialized from ")
{III}.append(path.toString())
{III}.append(", ")
{III}.append("but got ")
{III}.append(errors.size())
{III}.append(" error(s):")
{III}.append(System.lineSeparator());
{II}for (Reporting.Error error : errors) {{
{III}stringBuilder
{IIII}.append(Reporting.generateJsonPath(error.getPathSegments()))
{IIII}.append(": ")
{IIII}.append(error.getCause());
{II}}}
{II}fail(stringBuilder.toString());
{I}}}
}}""",
        ),
        Stripped(
            f"""\
public static void assertEqualsExpectedOrRerecordVerificationErrors(
{I}List<Reporting.Error> errors, Path path) throws IOException {{
{I}if (errors.isEmpty()) {{
{II}fail("Expected at least one verification error when verifying " + path + ", but got none");
{I}}}
{I}final String got =
{II}errors.stream()
{III}.map(
{IIII}error ->
{IIIII}Reporting.generateJsonPath(error.getPathSegments()) + ": " + error.getCause())
{IIIIII}.collect(Collectors.joining(";\\n"));
{I}final Path errorsPath = Paths.get(path + ".errors");
{I}if (RECORD_MODE) {{
{II}Files.write(errorsPath, got.getBytes(StandardCharsets.UTF_8));
{I}}} else {{
{II}if (!Files.exists(errorsPath)) {{
{III}throw new FileNotFoundException(
{IIII}"The file with the recorded errors does not exist: "
{IIIII}+ errorsPath
{IIIII}+ "; maybe you want to set the environment variable "
{IIIII}+ Common.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME);
{II}}}
{II}final String expected = String.join("\\n", Files.readAllLines(errorsPath));
{II}assertEquals(
{III}expected,
{III}got,
{III}"The expected verification errors do not match the actual ones for the file " + path);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
public static String trace(IClass instance)
{{
{I}return instance.getClass().getName();
}}"""
        ),
    ]

    blocks_joined = "\n\n".join(blocks)

    content = f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.fail;

import {package}.reporting.Reporting;
import {package}.types.model.IClass;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

/**
 * Provide common functionality to be re-used across different tests
 * such as reading of environment variables.
 */
public class Common {{
{I}public static String TEST_DATA_DIR = Paths.get("test_data").toAbsolutePath().toString();

{I}{indent_but_first_line(blocks_joined, I)}
}} // class Common

{java_common.WARNING}
"""

    return [java_common.JavaFile("Common.java", content)]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
