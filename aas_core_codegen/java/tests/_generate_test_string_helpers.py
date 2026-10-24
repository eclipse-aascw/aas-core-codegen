"""Generate the unit tests for the helpers of the operations on strings."""

import re
from typing import List

from icontract import require

from aas_core_codegen import string_helper_cases
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)
from aas_core_codegen.java import common as java_common
from aas_core_codegen.java.common import INDENT as I, INDENT2 as II, INDENT3 as III


def _method_name(prefix: str, description: str) -> str:
    """Derive the name of a test method from the ``description`` of a case."""
    words = re.split(r"[^a-zA-Z0-9]+", description)
    return f"test{prefix}" + "".join(word.capitalize() for word in words if word)


@require(lambda type_inference: intermediate_uses.string_operations(type_inference))
def generate(
    package: java_common.PackageIdentifier,
    type_inference: intermediate_type_inference.TypeInference,
) -> List[java_common.JavaFile]:
    """Generate the unit tests for the helpers of the operations on strings."""
    blocks: List[Stripped] = []

    if intermediate_uses.string_len_call(type_inference):
        for len_case in string_helper_cases.LEN_CASES:
            display_name = java_common.string_literal(
                f"{len_case.python_expression()} gives {len_case.expected}: "
                f"{len_case.description}"
            )

            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Len", len_case.description)}() {{
{I}assertEquals(
{II}{len_case.expected},
{II}StringHelpers.len({java_common.string_literal(len_case.text)}));
}}"""
                )
            )

    if intermediate_uses.string_slicing(type_inference):
        for slice_case in string_helper_cases.SLICE_CASES:
            display_name = java_common.string_literal(
                f"{slice_case.python_expression()} gives {slice_case.expected!r}: "
                f"{slice_case.description}"
            )

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            args = [
                java_common.string_literal(slice_case.text),
                "0" if slice_case.start is None else str(slice_case.start),
            ]
            if slice_case.end is not None:
                args.append(str(slice_case.end))

            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Slice", slice_case.description)}() {{
{I}assertEquals(
{II}{java_common.string_literal(slice_case.expected)},
{II}StringHelpers.slice({", ".join(args)}));
}}"""
                )
            )

    if intermediate_uses.string_find_call(type_inference):
        for find_case in string_helper_cases.FIND_CASES:
            display_name = java_common.string_literal(
                f"{find_case.python_expression()} gives {find_case.expected}: "
                f"{find_case.description}"
            )

            text = java_common.string_literal(find_case.text)
            sub = java_common.string_literal(find_case.sub)

            # NOTE (mristin):
            # We call the helper just as the transpiled code does.
            args = [text, sub]
            if find_case.start is not None:
                args.append(str(find_case.start))

            call = f"StringHelpers.find({', '.join(args)})"

            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Find", find_case.description)}() {{
{I}assertEquals({find_case.expected}, {call});
}}"""
                )
            )

    if intermediate_uses.string_ordering(type_inference):
        for compare_case in string_helper_cases.COMPARE_CASES:
            display_name = java_common.string_literal(
                f"{compare_case.python_expression()} gives {compare_case.expected}: "
                f"{compare_case.description}"
            )

            left = java_common.string_literal(compare_case.left)
            right = java_common.string_literal(compare_case.right)

            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Compare", compare_case.description)}() {{
{I}assertEquals(
{II}{compare_case.expected},
{II}Integer.signum(StringHelpers.compareByCodePoints({left}, {right})));
}}"""
                )
            )

    if intermediate_uses.lstrip_call(type_inference):
        for lstrip_case in string_helper_cases.LSTRIP_CASES:
            display_name = java_common.string_literal(
                f"{lstrip_case.python_expression()} gives "
                f"{lstrip_case.expected!r}: {lstrip_case.description}"
            )

            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Lstrip", lstrip_case.description)}() {{
{I}assertEquals(
{II}{java_common.string_literal(lstrip_case.expected)},
{II}StringHelpers.lstrip(
{III}{java_common.string_literal(lstrip_case.text)},
{III}{java_common.string_literal(lstrip_case.chars)}));
}}"""
                )
            )

    if intermediate_uses.rstrip_call(type_inference):
        for rstrip_case in string_helper_cases.RSTRIP_CASES:
            display_name = java_common.string_literal(
                f"{rstrip_case.python_expression()} gives "
                f"{rstrip_case.expected!r}: {rstrip_case.description}"
            )

            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Rstrip", rstrip_case.description)}() {{
{I}assertEquals(
{II}{java_common.string_literal(rstrip_case.expected)},
{II}StringHelpers.rstrip(
{III}{java_common.string_literal(rstrip_case.text)},
{III}{java_common.string_literal(rstrip_case.chars)}));
}}"""
                )
            )

    if intermediate_uses.startswith_call(type_inference):
        for startswith_case in string_helper_cases.STARTSWITH_CASES:
            display_name = java_common.string_literal(
                f"{startswith_case.python_expression()} gives "
                f"{startswith_case.expected!r}: {startswith_case.description}"
            )

            assertion = "assertTrue" if startswith_case.expected else "assertFalse"

            # NOTE (mristin):
            # We call the native method just as the transpiled code does.
            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Startswith", startswith_case.description)}() {{
{I}{assertion}(
{II}{java_common.string_literal(startswith_case.text)}.startsWith(
{III}{java_common.string_literal(startswith_case.prefix)}));
}}"""
                )
            )

    if intermediate_uses.endswith_call(type_inference):
        for endswith_case in string_helper_cases.ENDSWITH_CASES:
            display_name = java_common.string_literal(
                f"{endswith_case.python_expression()} gives "
                f"{endswith_case.expected!r}: {endswith_case.description}"
            )

            assertion = "assertTrue" if endswith_case.expected else "assertFalse"

            # NOTE (mristin):
            # We call the native method just as the transpiled code does.
            blocks.append(
                Stripped(
                    f"""\
@Test
@DisplayName({display_name})
public void {_method_name("Endswith", endswith_case.description)}() {{
{I}{assertion}(
{II}{java_common.string_literal(endswith_case.text)}.endsWith(
{III}{java_common.string_literal(endswith_case.suffix)}));
}}"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    # NOTE (mristin):
    # We import only what the tests use, since the common package has no
    # ``StringHelpers`` if the meta-model only uses the native operations.
    static_imports = [
        f"import static org.junit.jupiter.api.Assertions.{assertion};"
        for assertion in ("assertEquals", "assertFalse", "assertTrue")
        if any(f"{assertion}(" in block for block in blocks)
    ]

    imports = static_imports + [""]
    if any("StringHelpers." in block for block in blocks):
        imports.append(f"import {package}.common.StringHelpers;")

    imports_joined = "\n".join(imports)

    return [
        java_common.JavaFile(
            "TestStringHelpers.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

{imports_joined}
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Test the operations on strings.
 *
 * <p>The operations follow the Python implementation, since Python is
 * the language of the meta-model specifications. Hence, they work on
 * the characters (code points) of the strings. The expected values have been
 * computed with Python, and all the SDKs test against the very same cases.
 */
public class TestStringHelpers {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestStringHelpers

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
