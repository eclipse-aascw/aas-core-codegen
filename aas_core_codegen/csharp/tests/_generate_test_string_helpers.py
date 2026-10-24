"""Generate the unit tests for the helpers of the operations on strings."""

import re
from typing import List

from icontract import ensure, require

from aas_core_codegen import string_helper_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)
from aas_core_codegen.csharp import common as csharp_common
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _method_name(prefix: str, description: str) -> str:
    """Derive the name of a test method from the ``description`` of a case."""
    words = re.split(r"[^a-zA-Z0-9]+", description)
    return f"Test_{prefix}_" + "_".join(word for word in words if word)


# fmt: off
@require(
    lambda type_inference: intermediate_uses.string_operations(type_inference)
)
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    namespace: csharp_common.NamespaceIdentifier,
    type_inference: intermediate_type_inference.TypeInference,
) -> str:
    """
    Generate the unit tests for the helpers of the operations on strings.

    The ``namespace`` indicates the fully-qualified name of the base project.
    """
    blocks: List[Stripped] = []

    if intermediate_uses.string_len_call(type_inference):
        for len_case in string_helper_cases.LEN_CASES:
            description = csharp_common.string_literal(
                f"{len_case.python_expression()} gives {len_case.expected}: "
                f"{len_case.description}"
            )

            method_name = _method_name("len", len_case.description)

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{len_case.expected},
{II}Our.Common.StringHelpers.Len(
{III}{csharp_common.string_literal(len_case.text)}));
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.string_slicing(type_inference):
        for slice_case in string_helper_cases.SLICE_CASES:
            description = csharp_common.string_literal(
                f"{slice_case.python_expression()} gives {slice_case.expected!r}: "
                f"{slice_case.description}"
            )

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            args = [
                csharp_common.string_literal(slice_case.text),
                "0" if slice_case.start is None else str(slice_case.start),
            ]
            if slice_case.end is not None:
                args.append(str(slice_case.end))

            method_name = _method_name("slice", slice_case.description)

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{csharp_common.string_literal(slice_case.expected)},
{II}Our.Common.StringHelpers.Slice({", ".join(args)}));
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.string_find_call(type_inference):
        for find_case in string_helper_cases.FIND_CASES:
            description = csharp_common.string_literal(
                f"{find_case.python_expression()} gives {find_case.expected}: "
                f"{find_case.description}"
            )

            text = csharp_common.string_literal(find_case.text)
            sub = csharp_common.string_literal(find_case.sub)

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            args = [text, sub]
            if find_case.start is not None:
                args.append(str(find_case.start))

            call = f"Our.Common.StringHelpers.Find({', '.join(args)})"

            method_name = _method_name("find", find_case.description)

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{find_case.expected},
{II}{call});
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.string_ordering(type_inference):
        for compare_case in string_helper_cases.COMPARE_CASES:
            description = csharp_common.string_literal(
                f"{compare_case.python_expression()} gives {compare_case.expected}: "
                f"{compare_case.description}"
            )

            left = csharp_common.string_literal(compare_case.left)
            right = csharp_common.string_literal(compare_case.right)

            method_name = _method_name("compare", compare_case.description)

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{compare_case.expected},
{II}System.Math.Sign(
{III}Our.Common.StringHelpers.CompareByCodePoints({left}, {right})));
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.lstrip_call(type_inference):
        for lstrip_case in string_helper_cases.LSTRIP_CASES:
            description = csharp_common.string_literal(
                f"{lstrip_case.python_expression()} gives {lstrip_case.expected!r}: "
                f"{lstrip_case.description}"
            )

            method_name = _method_name("lstrip", lstrip_case.description)

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{csharp_common.string_literal(lstrip_case.expected)},
{II}Our.Common.StringHelpers.LStrip(
{III}{csharp_common.string_literal(lstrip_case.text)},
{III}{csharp_common.string_literal(lstrip_case.chars)}));
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.rstrip_call(type_inference):
        for rstrip_case in string_helper_cases.RSTRIP_CASES:
            description = csharp_common.string_literal(
                f"{rstrip_case.python_expression()} gives {rstrip_case.expected!r}: "
                f"{rstrip_case.description}"
            )

            method_name = _method_name("rstrip", rstrip_case.description)

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.AreEqual(
{II}{csharp_common.string_literal(rstrip_case.expected)},
{II}Our.Common.StringHelpers.RStrip(
{III}{csharp_common.string_literal(rstrip_case.text)},
{III}{csharp_common.string_literal(rstrip_case.chars)}));
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.startswith_call(type_inference):
        for startswith_case in string_helper_cases.STARTSWITH_CASES:
            description = csharp_common.string_literal(
                f"{startswith_case.python_expression()} gives "
                f"{startswith_case.expected!r}: {startswith_case.description}"
            )

            method_name = _method_name("startswith", startswith_case.description)
            assertion = "IsTrue" if startswith_case.expected else "IsFalse"

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.{assertion}(
{II}{csharp_common.string_literal(startswith_case.text)}.StartsWith(
{III}{csharp_common.string_literal(startswith_case.prefix)},
{III}System.StringComparison.Ordinal));
}}  // void {method_name}"""
                )
            )

    if intermediate_uses.endswith_call(type_inference):
        for endswith_case in string_helper_cases.ENDSWITH_CASES:
            description = csharp_common.string_literal(
                f"{endswith_case.python_expression()} gives "
                f"{endswith_case.expected!r}: {endswith_case.description}"
            )

            method_name = _method_name("endswith", endswith_case.description)
            assertion = "IsTrue" if endswith_case.expected else "IsFalse"

            blocks.append(
                Stripped(
                    f"""\
[Test, Description({description})]
public void {method_name}()
{{
{I}Assert.{assertion}(
{II}{csharp_common.string_literal(endswith_case.text)}.EndsWith(
{III}{csharp_common.string_literal(endswith_case.suffix)},
{III}System.StringComparison.Ordinal));
}}  // void {method_name}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return f"""\
{csharp_common.WARNING}

using Our = {namespace};  // renamed

using NUnit.Framework;  // can't alias

namespace {namespace}.Tests
{{
{I}/// <summary>
{I}/// Test the operations on strings.
{I}/// </summary>
{I}/// <remarks>
{I}/// The operations follow the Python implementation, since Python is
{I}/// the language of the meta-model specifications. Hence, they work on
{I}/// the characters (code points) of the strings. The expected values have been
{I}/// computed with Python, and all the SDKs test against the very same cases.
{I}/// </remarks>
{I}public class TestStringHelpers
{I}{{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}  // class TestStringHelpers
}}  // namespace {namespace}.Tests

{csharp_common.WARNING}
"""


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
