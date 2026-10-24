"""Generate code to test verification helpers and functions."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import INDENT as I


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code to test verification helpers and functions."""
    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test verification helper classes and string-based verification functions.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as OurTypes from "../src/types";
import * as OurVerification from "../src/verification";"""
        ),
        Stripped(
            f"""\
test("verification path and segments format", () => {{
{I}const path = new OurVerification.Path();

{I}path.prepend(
{I}{I}new OurVerification.IndexSegment(
{I}{I}{I}<Array<OurTypes.Class>>[],
{I}{I}{I}2
{I}{I})
{I});
{I}path.prepend(
{I}{I}new OurVerification.PropertySegment(
{I}{I}{I}<OurTypes.Class>{{}},
{I}{I}{I}"something"
{I}{I})
{I});

{I}expect(path.toString()).toStrictEqual(".something[2]");
}});"""
        ),
        Stripped(
            f"""\
test("verification error stores provided path", () => {{
{I}const path = new OurVerification.Path();
{I}path.prepend(
{I}{I}new OurVerification.PropertySegment(
{I}{I}{I}<OurTypes.Class>{{}},
{I}{I}{I}"idShort"
{I}{I})
{I});

{I}const error = new OurVerification.VerificationError(
{I}{I}"Some verification error",
{I}{I}path
{I});

{I}expect(error.message).toStrictEqual("Some verification error");
{I}expect(error.path.toString()).toStrictEqual(".idShort");
}});"""
        ),
    ]

    for verification in symbol_table.verification_functions:
        if verification.visibility is not intermediate.Visibility.PUBLIC:
            continue

        if len(verification.arguments) != 1:
            continue

        arg_type = verification.arguments[0].type_annotation
        if not isinstance(arg_type, intermediate.PrimitiveTypeAnnotation):
            continue

        if arg_type.a_type != intermediate.PrimitiveType.STR:
            continue

        # NOTE (mristin):
        # A verification function might also return a value other than a boolean,
        # and, given an arbitrary text, legitimately throw, *e.g.*, if it parses
        # an integer which the caller has to check beforehand.
        if not (
            isinstance(verification.returns, intermediate.PrimitiveTypeAnnotation)
            and verification.returns.a_type is intermediate.PrimitiveType.BOOL
        ):
            continue

        verification_name = typescript_naming.function_name(verification.name)

        blocks.append(
            Stripped(
                f"""\
test("{verification_name} returns boolean", () => {{
{I}const resultOnEmpty = OurVerification.{verification_name}("");
{I}expect(typeof resultOnEmpty).toStrictEqual("boolean");

{I}const resultOnSample = OurVerification.{verification_name}("sample-value");
{I}expect(typeof resultOnSample).toStrictEqual("boolean");
}});"""
            )
        )

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
