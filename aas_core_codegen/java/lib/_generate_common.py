"""Generate code shared across the generated Java packages."""

from typing import List, Sequence

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.intermediate import (
    type_inference as intermediate_type_inference,
    uses as intermediate_uses,
)
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


#: Check whether a string contains a character; shared by ``lstrip`` and ``rstrip``
_CONTAINS_CODE_POINT = Stripped(
    f"""\
/**
 * Check whether {{@code text}} contains the character {{@code codePoint}}.
 *
 * @param text to be searched in
 * @param codePoint to be searched for
 * @return true if {{@code codePoint}} is one of the characters of {{@code text}}
 */
private static boolean containsCodePoint(String text, int codePoint) {{
{I}int offset = 0;
{I}while (offset < text.length()) {{
{II}final int other = text.codePointAt(offset);
{II}if (other == codePoint) {{
{III}return true;
{II}}}

{II}offset += Character.charCount(other);
{I}}}

{I}return false;
}}"""
)

#: Strip the characters from the start of a string as ``str.lstrip`` in Python
_LSTRIP = Stripped(
    f"""\
/**
 * Strip the longest prefix of {{@code text}} which consists only of
 * the characters listed in {{@code chars}}.
 *
 * <p>We follow the Python implementation of {{@code str.lstrip}}, since Python
 * is the language of the meta-model specifications. Hence, we strip
 * the characters (code points), and not the UTF-16 code units. For example,
 * we do not strip the first half of a surrogate pair when {{@code chars}}
 * contains another character with the same high surrogate.
 *
 * @param text to be stripped
 * @param chars to be stripped from the start of {{@code text}}
 * @return {{@code text}} without the stripped prefix
 */
public static String lstrip(String text, String chars) {{
{I}int offset = 0;
{I}while (offset < text.length()) {{
{II}final int codePoint = text.codePointAt(offset);
{II}if (!containsCodePoint(chars, codePoint)) {{
{III}break;
{II}}}

{II}offset += Character.charCount(codePoint);
{I}}}

{I}return text.substring(offset);
}}"""
)

#: Strip the characters from the end of a string as ``str.rstrip`` in Python
_RSTRIP = Stripped(
    f"""\
/**
 * Strip the longest suffix of {{@code text}} which consists only of
 * the characters listed in {{@code chars}}.
 *
 * <p>We follow the Python implementation of {{@code str.rstrip}}, since Python
 * is the language of the meta-model specifications. Hence, we strip
 * the characters (code points), and not the UTF-16 code units. For example,
 * we do not strip the second half of a surrogate pair when {{@code chars}}
 * contains another character with the same low surrogate.
 *
 * @param text to be stripped
 * @param chars to be stripped from the end of {{@code text}}
 * @return {{@code text}} without the stripped suffix
 */
public static String rstrip(String text, String chars) {{
{I}int offset = text.length();
{I}while (offset > 0) {{
{II}final int codePoint = text.codePointBefore(offset);
{II}if (!containsCodePoint(chars, codePoint)) {{
{III}break;
{II}}}

{II}offset -= Character.charCount(codePoint);
{I}}}

{I}return text.substring(0, offset);
}}"""
)

#: Parse a text as a safe integer; this is how we transpile the built-in ``int``
_PARSE_SAFE_INT = Stripped(
    f"""\
/**
 * Parse {{@code text}} as a safe integer.
 *
 * <p>The meta-model calls {{@code int}} on strings, and this is its
 * transpilation. We accept only an optional sign followed by the ASCII digits,
 * and only the safe integers, <i>i.e.</i>, the integers within
 * {{@code -(2^53 - 1)}} and {{@code 2^53 - 1}}, which a double-precision
 * floating-point number represents exactly. This way, all the SDKs behave
 * the same.
 *
 * <p>We do not use {{@link Long#parseLong(String)}} as it accepts the digits
 * of any script, and the range of all the 64-bit integers.
 *
 * @param text to be parsed
 * @return the parsed integer
 * @throws IllegalArgumentException if {{@code text}} is not a safe integer
 */
public static long parseSafeInt(String text) {{
{I}// This is 2^53 - 1.
{I}final long maxSafeInteger = 9007199254740991L;

{I}final int length = text.length();

{I}int offset = 0;
{I}boolean negative = false;
{I}if (length > 0 && (text.charAt(0) == '+' || text.charAt(0) == '-')) {{
{II}negative = text.charAt(0) == '-';
{II}offset = 1;
{I}}}

{I}if (offset == length) {{
{II}throw new IllegalArgumentException(
{III}"Expected an optional sign followed by the ASCII digits, but got: "
{III}+ text);
{I}}}

{I}long value = 0;
{I}for (int i = offset; i < length; i++) {{
{II}final char character = text.charAt(i);
{II}if (character < '0' || character > '9') {{
{III}throw new IllegalArgumentException(
{IIII}"Expected an optional sign followed by the ASCII digits, but got: "
{IIII}+ text);
{II}}}

{II}// NOTE (mristin):
{II}// The value can not overflow as we check the range after each digit.
{II}value = value * 10 + (character - '0');
{II}if (value > maxSafeInteger) {{
{III}throw new IllegalArgumentException(
{IIII}"Expected a safe integer, but got a text out of its range: " + text);
{II}}}
{I}}}

{I}return negative ? -value : value;
}}"""
)


def _generate_string_helpers(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Stripped:
    """
    Generate the helpers for the operations on strings in the transpiled code.

    The helpers follow the Python implementation, since Python is the language of
    the meta-model specifications. Hence, the lengths and the positions count
    the characters (code points), while the Java strings count the UTF-16 code
    units, where a character beyond the Basic Multilingual Plane takes two
    of them (a surrogate pair). Moreover, the native ``String.substring`` throws
    on the positions out of range, and neither ``substring`` nor ``indexOf`` count
    the negative positions from the end. We also accept the positions as
    ``long``'s, since our integers are ``long``'s in Java.

    Each helper is generated only if the meta-model uses the respective operation.
    We also compare the strings to sort the items of the set properties of strings.
    """
    uses_slicing = intermediate_uses.string_slicing(type_inference)
    uses_find = intermediate_uses.string_find_call(type_inference)
    uses_lstrip = intermediate_uses.lstrip_call(type_inference)
    uses_rstrip = intermediate_uses.rstrip_call(type_inference)

    methods: List[Stripped] = []

    if uses_slicing:
        methods.append(
            Stripped(
                f"""\
/**
 * Resolve {{@code position}} in a string of {{@code length}} as Python does
 * in slicing.
 *
 * <p>A negative position counts from the end, and the positions out of range
 * are clamped to the string.
 *
 * @param position to be resolved
 * @param length of the string
 * @return the resolved position within {{@code [0, length]}}
 */
private static int resolvePosition(long position, int length) {{
{I}if (position < 0) {{
{II}return (int) Math.max(position + length, 0);
{I}}}

{I}return (int) Math.min(position, length);
}}"""
            )
        )

    # NOTE (mristin):
    # The slicing and ``find`` measure the text with ``len``.
    if intermediate_uses.string_len_call(type_inference) or uses_slicing or uses_find:
        methods.append(
            Stripped(
                f"""\
/**
 * Count the characters (code points) of {{@code text}}.
 *
 * <p>We follow the Python implementation of {{@code len}}, since Python is
 * the language of the meta-model specifications. Hence, a character beyond
 * the Basic Multilingual Plane counts as one, unlike in {{@code text.length()}}.
 *
 * @param text to be measured
 * @return the number of characters
 */
public static int len(String text) {{
{I}return text.codePointCount(0, text.length());
}}"""
            )
        )

    if uses_slicing:
        methods.extend(
            [
                Stripped(
                    f"""\
/**
 * Slice {{@code text}} from {{@code start}} up to {{@code end}}, exclusive.
 *
 * <p>We follow the Python implementation of slicing, since Python is
 * the language of the meta-model specifications. Hence, the positions count
 * the characters (code points), a negative position counts from the end,
 * the positions out of range are clamped to the string, and the slice is empty
 * if {{@code start}} is not before {{@code end}}.
 *
 * @param text to be sliced
 * @param start of the slice, inclusive
 * @param end of the slice, exclusive
 * @return the slice
 */
public static String slice(String text, long start, long end) {{
{I}final int length = len(text);
{I}final int theStart = resolvePosition(start, length);
{I}final int theEnd = resolvePosition(end, length);

{I}if (theStart >= theEnd) {{
{II}return "";
{I}}}

{I}final int startOffset = text.offsetByCodePoints(0, theStart);
{I}final int endOffset = text.offsetByCodePoints(startOffset, theEnd - theStart);
{I}return text.substring(startOffset, endOffset);
}}"""
                ),
                Stripped(
                    f"""\
/**
 * Slice {{@code text}} from {{@code start}} up to its end.
 *
 * <p>See {{@link #slice(String, long, long)}} for the semantics.
 *
 * @param text to be sliced
 * @param start of the slice, inclusive
 * @return the slice
 */
public static String slice(String text, long start) {{
{I}return slice(text, start, Long.MAX_VALUE);
}}"""
                ),
            ]
        )

    if uses_find:
        methods.extend(
            [
                Stripped(
                    f"""\
/**
 * Find the first {{@code sub}} in {{@code text}} from {{@code start}} on.
 *
 * <p>We follow the Python implementation of {{@code str.find}}, since Python
 * is the language of the meta-model specifications. Hence, the positions count
 * the characters (code points), a negative {{@code start}} counts from the end,
 * and a {{@code start}} beyond the end of {{@code text}} gives -1.
 *
 * @param text to be searched in
 * @param sub to be searched for
 * @param start of the search
 * @return the position of {{@code sub}} in {{@code text}}, or -1 if not found
 */
public static long find(String text, String sub, long start) {{
{I}final int length = len(text);
{I}final long theStart = start < 0 ? Math.max(start + length, 0) : start;
{I}if (theStart > length) {{
{II}return -1;
{I}}}

{I}final int startOffset = text.offsetByCodePoints(0, (int) theStart);
{I}final int offset = text.indexOf(sub, startOffset);
{I}if (offset == -1) {{
{II}return -1;
{I}}}

{I}return theStart + text.codePointCount(startOffset, offset);
}}"""
                ),
                Stripped(
                    f"""\
/**
 * Find the first {{@code sub}} in {{@code text}}.
 *
 * <p>See {{@link #find(String, String, long)}} for the semantics.
 *
 * @param text to be searched in
 * @param sub to be searched for
 * @return the position of {{@code sub}} in {{@code text}}, or -1 if not found
 */
public static long find(String text, String sub) {{
{I}return find(text, sub, 0);
}}"""
                ),
            ]
        )

    # NOTE (mristin):
    # We also sort the items of the set properties of strings by their code points
    # so that all the SDKs serialize them in the same order.
    if intermediate_uses.string_ordering(
        type_inference
    ) or intermediate_uses.sets_of_strings_in_properties(symbol_table):
        methods.append(
            Stripped(
                f"""\
/**
 * Compare {{@code that}} and {{@code other}} by their code points.
 *
 * <p>We follow the Python implementation of the string comparison, since
 * Python is the language of the meta-model specifications.
 * {{@link String#compareTo}} compares the UTF-16 code units instead, which gives
 * a different order for the characters outside the Basic Multilingual Plane.
 *
 * @param that text to be compared
 * @param other text to compare against
 * @return negative, zero or positive if {{@code that}} comes before, is equal to
 * or comes after {{@code other}}, respectively
 */
public static int compareByCodePoints(String that, String other) {{
{I}int i = 0;
{I}int j = 0;
{I}while (i < that.length() && j < other.length()) {{
{II}final int thatCodePoint = that.codePointAt(i);
{II}final int otherCodePoint = other.codePointAt(j);
{II}if (thatCodePoint != otherCodePoint) {{
{III}return Integer.compare(thatCodePoint, otherCodePoint);
{II}}}

{II}i += Character.charCount(thatCodePoint);
{II}j += Character.charCount(otherCodePoint);
{I}}}

{I}return Integer.compare(that.length() - i, other.length() - j);
}}"""
            )
        )

    if uses_lstrip or uses_rstrip:
        methods.append(_CONTAINS_CODE_POINT)

    if uses_lstrip:
        methods.append(_LSTRIP)

    if uses_rstrip:
        methods.append(_RSTRIP)

    if intermediate_uses.int_call(symbol_table):
        methods.append(_PARSE_SAFE_INT)

    methods_joined = "\n\n".join(methods)

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

{I}{indent_but_first_line(methods_joined, I)}
}}"""
    )

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.common;"),
        code,
        java_common.WARNING,
    ]

    return Stripped("\n\n".join(blocks))


def _generate_set_helpers(
    package: java_common.PackageIdentifier,
    with_operations: bool,
    with_sorting: bool,
    with_sorting_of_strings: bool,
    ranked_enumerations: Sequence[intermediate.Enumeration],
) -> Stripped:
    """
    Generate the helpers for the operations on sets and for their sorting.

    Python gives a new set as the result of an operation, so the helpers copy
    the sets instead of mutating them in place, as the native ``retainAll`` and
    ``removeAll`` do. We generate them only ``with_operations``.

    The set properties are serialized as sorted arrays, and the items are
    verified in the sorted order. The order must be the same in all the targets,
    so the strings are compared by their code points with
    ``StringHelpers.compareByCodePoints``, and not by their UTF-16 code units as
    :py:meth:`String.compareTo` does. We generate the sorting only
    ``with_sorting``, and the sorting of strings only ``with_sorting_of_strings``.

    The literals of the ``ranked_enumerations`` are sorted by the code points of
    their serialized values. We rank them here, at the generation time, so that
    the generated code compares them without any stringification.
    """
    methods: List[Stripped] = []

    if with_operations:
        methods.append(
            Stripped(
                f"""\
/**
 * Give a new set of the items which are both in {{@code that}} and
 * in {{@code other}}.
 *
 * @param that set to be intersected
 * @param other set to intersect with
 * @param <T> type of the items
 * @return new set with the common items
 */
public static <T> Set<T> intersection(Set<T> that, Set<T> other) {{
{I}final Set<T> result = new HashSet<>(that);
{I}result.retainAll(other);
{I}return result;
}}"""
            )
        )

        methods.append(
            Stripped(
                f"""\
/**
 * Give a new set of the items which are in {{@code that}}, but not
 * in {{@code other}}.
 *
 * @param that set to be subtracted from
 * @param other set of the items to be left out
 * @param <T> type of the items
 * @return new set with the remaining items
 */
public static <T> Set<T> difference(Set<T> that, Set<T> other) {{
{I}final Set<T> result = new HashSet<>(that);
{I}result.removeAll(other);
{I}return result;
}}"""
            )
        )

    if with_sorting:
        methods.append(
            Stripped(
                f"""\
/**
 * Give the items of {{@code that}} in their natural order.
 *
 * <p>We use it for the booleans, where {{@code false}} comes before
 * {{@code true}}, and for the integers.
 *
 * @param that set to be sorted
 * @param <T> type of the items
 * @return new list of the sorted items
 */
public static <T extends Comparable<? super T>> List<T> sorted(
{I}Set<? extends T> that) {{
{I}final List<T> result = new ArrayList<>(that);
{I}Collections.sort(result);
{I}return result;
}}"""
            )
        )

    if with_sorting_of_strings:
        methods.append(
            Stripped(
                f"""\
/**
 * Give the texts of {{@code that}} sorted by their code points.
 *
 * @param that set to be sorted
 * @return new list of the sorted texts
 */
public static List<String> sortedByCodePoints(Set<String> that) {{
{I}final List<String> result = new ArrayList<>(that);
{I}result.sort(StringHelpers::compareByCodePoints);
{I}return result;
}}"""
            )
        )

    if with_sorting:
        methods.append(
            Stripped(
                f"""\
/**
 * Give the items of {{@code that}} sorted by {{@code comparator}}.
 *
 * <p>We use it for the enumeration literals, which we compare by their ranks.
 *
 * @param that set to be sorted
 * @param comparator to compare two items
 * @param <T> type of the items
 * @return new list of the sorted items
 */
public static <T> List<T> sortedBy(
{I}Set<? extends T> that, Comparator<? super T> comparator) {{
{I}final List<T> result = new ArrayList<>(that);
{I}result.sort(comparator);
{I}return result;
}}"""
            )
        )

    # NOTE (mristin):
    # The names of the helpers generated per enumeration start with ``rankOf``
    # and ``compareByRankOf``, respectively, while no fixed helper in this class
    # starts with either prefix. Hence a generated name can never equal nor
    # overload a fixed one, whatever the name of the enumeration, *e.g.*,
    # an enumeration ``By_code_points`` gives ``compareByRankOfByCodePoints``
    # and not ``compareByCodePoints``.
    for enumeration in ranked_enumerations:
        enum_name = java_naming.enum_name(enumeration.name)
        rank_name = java_naming.method_name(Identifier(f"rank_of_{enumeration.name}"))
        compare_name = java_naming.method_name(
            Identifier(f"compare_by_rank_of_{enumeration.name}")
        )

        # NOTE (mristin):
        # Python compares the strings by their code points, which is exactly
        # the order in which we sort the literals in all the targets.
        sorted_literals = sorted(
            enumeration.literals, key=lambda literal: literal.value
        )

        cases = "\n".join(
            f"case {java_naming.enum_literal_name(literal.name)}: "
            f"return {rank};  // {java_common.string_literal(literal.value)}"
            for rank, literal in enumerate(sorted_literals)
        )

        unknown_rank = len(sorted_literals)

        methods.append(
            Stripped(
                f"""\
/**
 * Rank the literal {{@code that}} of {{@link {enum_name}}} by the code points
 * of its serialized value.
 *
 * <p>A null or an unknown literal ranks last.
 *
 * @param that literal to be ranked
 * @return rank of the literal
 */
public static int {rank_name}({enum_name} that) {{
{I}if (that == null) {{
{II}return {unknown_rank};
{I}}}

{I}switch (that) {{
{II}{indent_but_first_line(cases, II)}
{II}default: return {unknown_rank};
{I}}}
}}"""
            )
        )

        methods.append(
            Stripped(
                f"""\
/**
 * Compare the literals {{@code that}} and {{@code other}} of
 * {{@link {enum_name}}} by their ranks.
 *
 * @param that literal to be compared
 * @param other literal to compare against
 * @return negative, zero or positive if {{@code that}} comes before, is equal to
 * or comes after {{@code other}}, respectively
 */
public static int {compare_name}({enum_name} that, {enum_name} other) {{
{I}return Integer.compare({rank_name}(that), {rank_name}(other));
}}"""
            )
        )

    methods_joined = "\n\n".join(methods)

    code = Stripped(
        f"""\
/**
 * Provide the operations on sets and the sorting of their items.
 */
public final class SetHelpers {{
{I}private SetHelpers() {{
{II}// Prevent instantiation
{I}}}

{I}{indent_but_first_line(methods_joined, I)}
}}"""
    )

    imports: List[str] = []
    if len(ranked_enumerations) > 0:
        imports.append(f"import {package}.types.enums.*;")
    if with_sorting:
        imports.extend(
            [
                "import java.util.ArrayList;",
                "import java.util.Collections;",
                "import java.util.Comparator;",
            ]
        )
    if with_operations:
        imports.append("import java.util.HashSet;")
    if with_sorting:
        imports.append("import java.util.List;")
    imports.append("import java.util.Set;")

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.common;"),
        Stripped("\n".join(imports)),
        code,
        java_common.WARNING,
    ]

    return Stripped("\n\n".join(blocks))


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> List[java_common.JavaFile]:
    """
    Generate code shared across the generated Java packages.

    The tuples are generated unconditionally, regardless of whether the meta-model
    actually uses them, since the ``Tuple1`` .. ``Tuple8`` records are generic
    infrastructure, and not meta-model-derived types.

    The string helpers are generated only if the meta-model might take ``len`` of
    strings, slice them, compare them, sort them in set properties, or call
    ``find``, ``lstrip``, ``rstrip`` or ``int`` on them. We transpile
    ``startswith`` and ``endswith`` to the native methods, so they do not need
    the string helpers.
    """
    files: List[java_common.JavaFile] = []

    if (
        intermediate_uses.string_len_call(type_inference)
        or intermediate_uses.string_slicing(type_inference)
        or intermediate_uses.string_find_call(type_inference)
        or intermediate_uses.string_ordering(type_inference)
        or intermediate_uses.lstrip_call(type_inference)
        or intermediate_uses.rstrip_call(type_inference)
        or intermediate_uses.sets_of_strings_in_properties(symbol_table)
        or intermediate_uses.int_call(symbol_table)
    ):
        files.append(
            java_common.JavaFile(
                "StringHelpers.java",
                f"{_generate_string_helpers(package, symbol_table, type_inference)}\n",
            )
        )

    with_operations = intermediate_uses.set_operations(symbol_table)
    with_sorting = java_common.has_set_properties(symbol_table)
    if with_operations or with_sorting:
        set_helpers = _generate_set_helpers(
            package=package,
            with_operations=with_operations,
            with_sorting=with_sorting,
            with_sorting_of_strings=intermediate_uses.sets_of_strings_in_properties(
                symbol_table
            ),
            ranked_enumerations=intermediate_uses.enumerations_in_set_properties(
                symbol_table
            ),
        )
        files.append(java_common.JavaFile("SetHelpers.java", f"{set_helpers}\n"))

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
{I}/**
{I} * Count the items of the tuple.
{I} */
{I}public int size() {{
{II}return {arity};
{I}}}
}}"""
        )

        blocks: List[Stripped] = [
            java_common.WARNING,
            Stripped(f"package {package}.common;"),
            record_code,
            java_common.WARNING,
        ]

        code = "\n\n".join(blocks)

        files.append(java_common.JavaFile(f"{name}.java", f"{code}\n"))

    return files


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
