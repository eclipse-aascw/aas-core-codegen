"""Generate code shared across the generated Java packages."""

from typing import List

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped
from aas_core_codegen.java import common as java_common
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _generate_string_helpers(package: java_common.PackageIdentifier) -> Stripped:
    """
    Generate the helpers for ``len``, slicing strings and ``find``.

    The helpers follow the Python implementation, since Python is the language of
    the meta-model specifications. Hence, the lengths and the positions count
    the characters (code points), while the Java strings count the UTF-16 code
    units, where a character beyond the Basic Multilingual Plane takes two
    of them (a surrogate pair). Moreover, the native ``String.substring`` throws
    on the positions out of range, and neither ``substring`` nor ``indexOf`` count
    the negative positions from the end. We also accept the positions as
    ``long``'s, since our integers are ``long``'s in Java.
    """
    # NOTE (mristin):
    # The native ``codePointCount`` and ``offsetByCodePoints`` count a lone
    # surrogate as a character of its own, as Python does. We do not check whether
    # ``indexOf`` matches in the middle of a surrogate pair, as that could only
    # happen if the searched text started or ended with a lone surrogate.
    code = Stripped(
        f"""\
/**
 * Provide string operations which follow the Python implementation, since
 * Python is the language of the meta-model specifications.
 *
 * <p>The lengths and the positions count the characters (code points), and not
 * the UTF-16 code units of the Java strings. Hence, a character beyond the Basic
 * Multilingual Plane counts as one, though it takes two UTF-16 code units
 * (a surrogate pair).
 */
public final class StringHelpers {{
{I}private StringHelpers() {{
{II}// Prevent instantiation
{I}}}

{I}/**
{I} * Resolve {{@code position}} in a string of {{@code length}} as Python does
{I} * in slicing.
{I} *
{I} * <p>A negative position counts from the end, and the positions out of range
{I} * are clamped to the string.
{I} *
{I} * @param position to be resolved
{I} * @param length of the string
{I} * @return the resolved position within {{@code [0, length]}}
{I} */
{I}private static int resolvePosition(long position, int length) {{
{II}if (position < 0) {{
{III}return (int) Math.max(position + length, 0);
{II}}}

{II}return (int) Math.min(position, length);
{I}}}

{I}/**
{I} * Count the characters (code points) of {{@code text}}.
{I} *
{I} * <p>We follow the Python implementation of {{@code len}}, since Python is
{I} * the language of the meta-model specifications. Hence, a character beyond
{I} * the Basic Multilingual Plane counts as one, unlike in {{@code text.length()}}.
{I} *
{I} * @param text to be measured
{I} * @return the number of characters
{I} */
{I}public static int len(String text) {{
{II}return text.codePointCount(0, text.length());
{I}}}

{I}/**
{I} * Slice {{@code text}} from {{@code start}} up to {{@code end}}, exclusive.
{I} *
{I} * <p>We follow the Python implementation of slicing, since Python is
{I} * the language of the meta-model specifications. Hence, the positions count
{I} * the characters (code points), a negative position counts from the end,
{I} * the positions out of range are clamped to the string, and the slice is empty
{I} * if {{@code start}} is not before {{@code end}}.
{I} *
{I} * @param text to be sliced
{I} * @param start of the slice, inclusive
{I} * @param end of the slice, exclusive
{I} * @return the slice
{I} */
{I}public static String slice(String text, long start, long end) {{
{II}final int length = len(text);
{II}final int theStart = resolvePosition(start, length);
{II}final int theEnd = resolvePosition(end, length);

{II}if (theStart >= theEnd) {{
{III}return "";
{II}}}

{II}final int startOffset = text.offsetByCodePoints(0, theStart);
{II}final int endOffset = text.offsetByCodePoints(startOffset, theEnd - theStart);
{II}return text.substring(startOffset, endOffset);
{I}}}

{I}/**
{I} * Slice {{@code text}} from {{@code start}} up to its end.
{I} *
{I} * <p>See {{@link #slice(String, long, long)}} for the semantics.
{I} *
{I} * @param text to be sliced
{I} * @param start of the slice, inclusive
{I} * @return the slice
{I} */
{I}public static String slice(String text, long start) {{
{II}return slice(text, start, Long.MAX_VALUE);
{I}}}

{I}/**
{I} * Find the first {{@code sub}} in {{@code text}} from {{@code start}} on.
{I} *
{I} * <p>We follow the Python implementation of {{@code str.find}}, since Python
{I} * is the language of the meta-model specifications. Hence, the positions count
{I} * the characters (code points), a negative {{@code start}} counts from the end,
{I} * and a {{@code start}} beyond the end of {{@code text}} gives -1.
{I} *
{I} * @param text to be searched in
{I} * @param sub to be searched for
{I} * @param start of the search
{I} * @return the position of {{@code sub}} in {{@code text}}, or -1 if not found
{I} */
{I}public static long find(String text, String sub, long start) {{
{II}final int length = len(text);
{II}final long theStart = start < 0 ? Math.max(start + length, 0) : start;
{II}if (theStart > length) {{
{III}return -1;
{II}}}

{II}final int startOffset = text.offsetByCodePoints(0, (int) theStart);
{II}final int offset = text.indexOf(sub, startOffset);
{II}if (offset == -1) {{
{III}return -1;
{II}}}

{II}return theStart + text.codePointCount(startOffset, offset);
{I}}}

{I}/**
{I} * Find the first {{@code sub}} in {{@code text}}.
{I} *
{I} * <p>See {{@link #find(String, String, long)}} for the semantics.
{I} *
{I} * @param text to be searched in
{I} * @param sub to be searched for
{I} * @return the position of {{@code sub}} in {{@code text}}, or -1 if not found
{I} */
{I}public static long find(String text, String sub) {{
{II}return find(text, sub, 0);
{I}}}
}}"""
    )

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.common;"),
        code,
        java_common.WARNING,
    ]  # type: List[Stripped]

    return Stripped("\n\n".join(blocks))


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code shared across the generated Java packages.

    The tuples are generated unconditionally, regardless of whether the meta-model
    actually uses them, since the ``Tuple1`` .. ``Tuple8`` records are generic
    infrastructure, and not meta-model-derived types.

    The string helpers are generated only if the meta-model might take ``len`` of
    strings, slice them or call ``find`` on them.
    """
    files = []  # type: List[java_common.JavaFile]

    if intermediate.uses_len_slicing_or_find(symbol_table):
        files.append(
            java_common.JavaFile(
                "StringHelpers.java", f"{_generate_string_helpers(package)}\n"
            )
        )

    for arity in range(1, java_common.MAX_TUPLE_ARITY + 1):
        name = f"Tuple{arity}"
        type_params = ", ".join(f"T{i + 1}" for i in range(arity))
        components = ", ".join(f"T{i + 1} item{i + 1}" for i in range(arity))

        record_code = Stripped(
            f"""\
/**
 * Represent a fixed-size heterogeneous tuple of {arity} item(s).
 */
public record {name}<{type_params}>({components}) {{
}}"""
        )

        blocks = [
            java_common.WARNING,
            Stripped(f"package {package}.common;"),
            record_code,
            java_common.WARNING,
        ]  # type: List[Stripped]

        code = "\n\n".join(blocks)

        files.append(java_common.JavaFile(f"{name}.java", f"{code}\n"))

    return files


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
