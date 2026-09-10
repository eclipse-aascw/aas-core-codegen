"""Generate the code for reporting errors."""

import io
import textwrap
from typing import List

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.java import (
    common as java_common,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def generate(package: java_common.PackageIdentifier) -> List[java_common.JavaFile]:
    """
    Generate the code for reporting errors.
    """

    blocks = [
        Stripped(
            f"""\
/**
 * Capture a path segment of a value in a model.
 */
public static abstract class Segment {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
public static class NameSegment extends Segment {{
{I}private final String name;
{I}public NameSegment(String name) {{
{II}this.name = Objects.requireNonNull(name,
{III}"Argument \\"name\\" must be non-null.");
{I}}}
{I}public String getName(){{
{II}return name;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
public static class IndexSegment extends Segment{{
{I}private final Integer index;
{I}public IndexSegment(int index) {{
{II}this.index = index;
{I}}}
{I}public Integer getIndex(){{
{II}return index;
{I}}}
}}"""
        ),
        Stripped(
            """\
private static final Pattern variableNameRe = Pattern.compile("^[a-zA-Z_][a-zA-Z_0-9]*$");"""
        ),
        Stripped(
            f"""\
/**
 * Generate a JSON Path based on the path segments.
 *
 * <p>See, for example, this page for more information on JSON path:
 * <a href="https://support.smartbear.com/alertsite/docs/monitors/api/endpoint/jsonpath.html"
 * >https://support.smartbear.com/alertsite/docs/monitors/api/endpoint/jsonpath.html</a>
 */
public static String generateJsonPath(Collection<Segment> segments) {{
{I}ArrayList<String> parts = new ArrayList<>(segments.size());
{I}int i = 0;

{I}for (Segment segment : segments) {{
{II}String part;

{II}if (segment instanceof NameSegment) {{
{III}NameSegment nameSegment = (NameSegment) segment;
{III}Matcher m = variableNameRe.matcher(nameSegment.getName());

{III}if (m.matches()) {{
{IIII}part = (i == 0) ? nameSegment.getName() : "." + nameSegment.getName();
{III}}} else {{
{IIII}String escaped = nameSegment.getName()
{IIIII}.replace("\\t", "\\\\t")
{IIIII}.replace("\\b", "\\\\b")
{IIIII}.replace("\\n", "\\\\n")
{IIIII}.replace("\\r", "\\\\r")
{IIIII}.replace("\\f", "\\\\f")
{IIIII}.replace("\\"", "\\\\\\"")
{IIIII}.replace("\\\\", "\\\\\\\\");

{IIII}part = "[\\"" + escaped + "\\"]";
{III}}}
{II}}} else if (segment instanceof IndexSegment) {{
{III}IndexSegment indexSegment = (IndexSegment) segment;
{III}part = "[" + indexSegment.getIndex() + "]";
{II}}} else {{
{III}throw new RuntimeException(
{IIII}"Unexpected segment type: " + segment.getClass().getSimpleName()
{III});
{II}}}

{II}parts.add(part);
{II}i++;
{I}}}
{I}return String.join("", parts);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Escape special characters for XPath.
 */
private static String escapeForXPath(String text) {{
return text
{II}.replace("&", "&amp;")
{II}.replace("/", "&#47;")
{II}.replace("<", "&lt;")
{II}.replace(">", "&gt;")
{II}.replace("\\"", "&quot;")
{II}.replace("'", "&apos;");
}}"""
        ),
        Stripped(
            f"""\
/**
 * Generate a relative XPath based on the path segments.
 *
 * <p>This method leaves out the leading slash ('/'). This is helpful if
 * to embed the error report in a larger document with a prefix etc.
 */
public static String generateRelativeXPath(Collection<Segment> segments) {{
{I}final List<String> parts = new ArrayList<>();
{I}segments.forEach(segment -> {{
{II}String part;
{II}if (segment instanceof NameSegment) {{
{III}final NameSegment nameSegment = ((NameSegment) segment);
{III}final String name = nameSegment.getName();
{III}part = escapeForXPath(name);
{II}}} else if (segment instanceof IndexSegment) {{
{III}final IndexSegment indexSegment = ((IndexSegment) segment);
{III}final int index = indexSegment.getIndex();
{III}part = "*[" + index + "]";
{II}}} else {{
{III}throw new IllegalArgumentException("Unexpected segment type: " +
{IIII}segment.getClass().getSimpleName());
{II}}}
{II}parts.add(part);
{I}}});
{I}return String.join("/", parts);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an error during the deserialization or the verification.
 */
public static class Error {{
{I}private final Deque<Segment> pathSegments = new LinkedList<>();
{I}private final String cause;

{I}public Error(String cause) {{
{II}this.cause = cause;
{I}}}

{I}public void prependSegment(Segment segment) {{
{II}pathSegments.addFirst(segment);
{I}}}

{I}public String getCause() {{
{II}return cause;
{I}}}

{I}public Collection<Segment> getPathSegments() {{
{II}return pathSegments;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent the outcome of a de/serialization or a verification step.
 *
 * <p>This is shared by JSON de/serialization, XML de/serialization and
 * verification, all of which propagate an {{@link Error}} instead of relying
 * on exceptions for the common (successful) case.
 */
public static class Result<T> {{
{I}private final T result;
{I}private final Error error;
{I}private final boolean success;

{I}private Result(T result, Error error, boolean success) {{
{II}this.result = result;
{II}this.error = error;
{II}this.success = success;
{I}}}

{I}public static <T> Result<T> success(T result) {{
{II}if (result == null) throw new IllegalArgumentException("Result must not be null.");
{II}return new Result<>(result, null, true);
{I}}}

{I}public static <T> Result<T> failure(Error error) {{
{II}if (error == null) throw new IllegalArgumentException("Error must not be null.");
{II}return new Result<>(null, error, false);
{I}}}

{I}@SuppressWarnings("unchecked")
{I}public <I> Result<I> castTo(Class<I> type) {{
{II}if (isError() || type.isInstance(result)) return (Result<I>) this;
{II}throw new IllegalStateException("Result of type "
{III}+ result.getClass().getName()
{III}+ " is not an instance of "
{III}+ type.getName());
{I}}}

{I}public T getResult() {{
{II}if (!isSuccess()) throw new IllegalStateException("Result is not present.");
{II}return result;
{I}}}

{I}public boolean isSuccess() {{
{II}return success;
{I}}}

{I}public boolean isError() {{
{II}return !success;
{I}}}

{I}public Error getError() {{
{II}if (isSuccess()) throw new IllegalStateException("Result is present.");
{II}return error;
{I}}}

{I}public <R> R map(Function<T, R> successFunction, Function<Error, R> errorFunction) {{
{II}return isSuccess() ? successFunction.apply(result) : errorFunction.apply(error);
{I}}}

{I}public T onError(Function<Error, T> errorFunction) {{
{II}return map(Function.identity(), errorFunction);
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    writer.write(
        f"""\
package {package}.reporting;

import java.util.ArrayList;
import java.util.Deque;
import java.util.Collections;
import java.util.Collection;
import java.util.List;
import java.util.LinkedList;
import java.util.Objects;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Provide reporting for de/serialization and verification.
 */
public class Reporting
{{
"""
    )

    for i, deserialize_block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(deserialize_block, I))

    writer.write("\n}")

    blocks = [
        java_common.WARNING,
        Stripped(writer.getvalue()),
        java_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return [java_common.JavaFile("Reporting.java", writer.getvalue())]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
