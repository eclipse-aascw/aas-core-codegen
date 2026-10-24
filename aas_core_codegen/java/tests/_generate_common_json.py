"""Generate code for shared JSON functionality across unit tests."""

from typing import List

from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import (
    common as java_common,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def generate(package: java_common.PackageIdentifier) -> List[java_common.JavaFile]:
    """
    Generate code for shared JSON functionality across unit tests.
    """
    blocks = [
        Stripped(
            f"""\
public static JsonNode readFromFile(Path path) {{
{I}final ObjectMapper objectMapper = new ObjectMapper();

{I}JsonNode node;
{I}try {{
{II}node = objectMapper.readTree(path.toFile());
{I}}} catch (JsonParseException exception) {{
{II}throw new IllegalStateException(
{III}"Expected the file to be a valid JSON, but it was not: "
{IIII}+ path + "; exception was: "
{IIII}+ exception);
{I}}} catch (JsonProcessingException exception) {{
{II}throw new IllegalStateException(
{III}"Expected the file to be a valid JSON, but it was not: "
{IIII}+ path + "; exception was: "
{IIII}+ exception);
{I}}} catch (IOException exception) {{
{II}throw new IllegalStateException(
{III}"Expected the file to be a valid JSON, but it was not: "
{IIII}+ path + "; exception was: "
{IIII}+ exception);
{I}}}
{I}return node;
}}"""
        ),
        Stripped(
            f"""\
/**
 *  Serialize something to a uniform JSON text
 *  such that we can use it for comparisons in the tests.
 */
public static JsonNode toJson(Object something)
{{
{I}if (something instanceof Boolean) {{
{II}return BooleanNode.valueOf((Boolean) something);
{I}}} else if (something instanceof Integer) {{
{II}return IntNode.valueOf((Integer) something);
{I}}} else if (something instanceof Double) {{
{II}return DoubleNode.valueOf((Double) something);
{I}}} else if (something instanceof String) {{
{II}return TextNode.valueOf((String) something);
{I}}} else if (something instanceof byte[]) {{
{II}return BinaryNode.valueOf((byte[]) something);
{I}}} else if (something instanceof IClass) {{
{II}return Jsonization.Serialize.toJsonObject((IClass) something);
{I}}} else if (something instanceof JsonNode) {{
{II}return (JsonNode) something;
{I}}} else {{
{II}throw new IllegalArgumentException(
{III}"The conversion of type "
{IIII}+ something.getClass().toString()
{IIII}+ " to a JSON node has not been defined: "
{IIII}+ something.toString());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Infer the node kind of the JSON node.
 */
// TODO check whether this is really necessary
private static String getNodeKind(JsonNode node)
{{
{I}if (node.isArray()) {{
{II}return "array";
{I}}} else if (node.isObject()) {{
{II}return "object";
{I}}} else if (node.isValueNode()) {{
{II}return "value";
{I}}} else {{
{II}throw new IllegalStateException(
{III}"Unhandled JsonNode: " + node.getNodeType().toString());
{I}}}
}}"""
        ),
    ]  # type: List[Stripped]

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "CommonJson.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.jsonization.Jsonization;
import {package}.types.impl.*;
import {package}.types.model.*;
import com.fasterxml.jackson.core.JsonParseException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.*;
import java.io.IOException;
import java.nio.file.Path;

public final class CommonJson {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // public final class CommonJson

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
