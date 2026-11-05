# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate code for common functionality shared across the tests."""
import re

from icontract import ensure

from aas_core_codegen.common import Stripped, Identifier, indent_but_first_line
from aas_core_codegen.csharp import (
    common as csharp_common,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _namespace_to_upper_snake(
    namespace: csharp_common.NamespaceIdentifier,
) -> Identifier:
    """
    Convert a CamelCase dotted namespace into UPPER_SNAKE_CASE.

    >>> _namespace_to_upper_snake(csharp_common.NamespaceIdentifier("AasCore.Aas3_1"))
    'AAS_CORE_AAS3_1'

    >>> _namespace_to_upper_snake(csharp_common.NamespaceIdentifier("SimpleTest"))
    'SIMPLE_TEST'

    >>> _namespace_to_upper_snake(csharp_common.NamespaceIdentifier("Already_Snake"))
    'ALREADY_SNAKE'
    """
    result = namespace.replace(".", "_")

    # Insert underscore between lowercase and uppercase (aasCore → aas_Core)
    result = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", result)

    return Identifier(result.upper())


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(namespace: csharp_common.NamespaceIdentifier) -> str:
    """
    Generate code for common functionality shared across the tests.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks = [
        Stripped(
            f"""\
public static readonly string RecordModeEnvironmentVariableName = (
{I}"{_namespace_to_upper_snake(namespace)}_TESTS_RECORD_MODE"
);"""
        ),
        Stripped(
            f"""\
// NOTE (mristin):
// It is tedious to record manually all the expected error messages.
// Therefore we include this variable to steer the automatic recording.
// We intentionally inter-twine the recording code with the test code
// to keep them close to each other so that they are easier to maintain.
public static readonly bool RecordMode = (
{I}System.Environment.GetEnvironmentVariable(
{II}RecordModeEnvironmentVariableName
{I})?.ToLower()
{II}== "true"
{I}|| System
{II}.Environment.GetEnvironmentVariable(RecordModeEnvironmentVariableName)
{II}?.ToLower() == "on"
{I}|| System
{II}.Environment.GetEnvironmentVariable(RecordModeEnvironmentVariableName)
{II}?.ToLower() == "1"
{I}|| System
{II}.Environment.GetEnvironmentVariable(RecordModeEnvironmentVariableName)
{II}?.ToLower() == "yes"
);"""
        ),
        Stripped(
            f"""\
public static readonly string TestDataDir = (
{I}System.Environment.GetEnvironmentVariable(
{II}"{_namespace_to_upper_snake(namespace)}_TESTS_TEST_DATA_DIR"
{I})
{I}?? throw new System.InvalidOperationException(
{II}"The path to the test data directory is missing in the environment: "
{III}+ "{_namespace_to_upper_snake(namespace)}_TESTS_TEST_DATA_DIR"
{I})
);"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Find the first instance of <typeparamref name="T"/>
/// in the <paramref name="container" />,
/// including the <paramref name="container" /> itself.
/// </summary>
public static T MustFind<T>(Our.IClass container)
{I}where T : Our.IClass
{{
{I}var instance = (
{II}(container is T)
{III}? container
{III}: container.Descend().First(something => something is T)
{III}?? throw new System.InvalidOperationException(
{IIII}    $"No instance of {{nameof(T)}} could be found"
{IIII})
{I});

{I}return (T)instance;
}}"""
        ),
        Stripped(
            f"""\
public static void AssertNoVerificationErrors(
{I}List<Our.Reporting.Error> errors,
{I}string path
)
{{
{I}if (errors.Count > 0)
{I}{{
{II}var builder = new System.Text.StringBuilder();
{II}builder.Append(
{III}$"Expected no errors when verifying the instance de-serialized from {{path}}, "
{IIII}+ $"but got {{errors.Count}} error(s):\\n"
{II});
{II}for (var i = 0; i < errors.Count; i++)
{II}{{
{III}builder.Append(
{IIII}$"Error {{i + 1}}:\\n"
{IIIII}+ $"{{Reporting.GenerateJsonPath(errors[i].PathSegments)}}: "
{IIIII}+ $"{{errors[i].Cause}}\\n"
{III});
{II}}}

{II}Assert.Fail(builder.ToString());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
public static void AssertEqualsExpectedOrRerecordVerificationErrors(
{I}List<Our.Reporting.Error> errors,
{I}string path
)
{{
{I}if (errors.Count == 0)
{I}{{
{II}Assert.Fail(
{III}$"Expected at least one verification error when verifying {{path}}, "
{IIII}+ "but got none"
{II});
{I}}}

{I}string got = string.Join(
{II}";\\n",
{II}errors.Select(error =>
{III}$"{{Reporting.GenerateJsonPath(error.PathSegments)}}: {{error.Cause}}"
{II})
{I});

{I}string errorsPath = path + ".errors";
{I}if (RecordMode)
{I}{{
{II}System.IO.File.WriteAllText(errorsPath, got);
{I}}}
{I}else
{I}{{
{II}if (!System.IO.File.Exists(errorsPath))
{II}{{
{III}throw new System.IO.FileNotFoundException(
{IIII}"The file with the recorded errors does not "
{IIIII}+ $"exist: {{errorsPath}}; maybe you want to set "
{IIIII}+ "the environment variable "
{IIIII}+ $"{{Our.Tests.Common.RecordModeEnvironmentVariableName}}?"
{III});
{II}}}

{II}string expected = System.IO.File.ReadAllText(errorsPath);
{II}Assert.AreEqual(
{III}expected.Replace("\\r\\n", "\\n"),
{III}got.Replace("\\r\\n", "\\n"),
{III}$"The expected verification errors do not match the actual ones for the file {{path}}"
{II});
{I}}}
}}"""
        ),
        Stripped(
            f"""\
public static string Trace(Our.IClass instance)
{{
{I}return instance.GetType().Name;
}}"""
        ),
    ]

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace}; // renamed

using System.Collections.Generic; // can't alias
using System.Linq; // can't alias
using NUnit.Framework; // can't alias

namespace {namespace}.Tests
{{
{I}/// <summary>
{I}/// Provide common functionality to be re-used across different tests
{I}/// such as reading of environment variables.
{I}/// </summary>
{I}public static class Common
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // public static class Common
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
