"""Generate code to test the JSON de/serialization of concrete classes."""

from typing import List

from aas_core_codegen import intermediate, naming
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_serialization_failure_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the tests that a number unrepresentable in JSON is refused."""
    result: List[Stripped] = []

    for numeric_place in intermediate.numeric_places(symbol_table):
        if numeric_place.a_type is intermediate.PrimitiveType.FLOAT:
            value_type = "double"
            zero_literal = "0.0"
            what = "NonFinite"
            values_literal = (
                "{Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY, Double.NaN}"
            )
        else:
            value_type = "long"
            zero_literal = "0L"
            what = "OutOfRange"
            values_literal = "{9007199254740992L, -9007199254740992L}"

        setter_name = java_naming.method_name(
            Identifier(f"set_{numeric_place.prop.name}")
        )
        getter_name = java_naming.getter_name(numeric_place.prop.name)

        # NOTE (mristin):
        # A serialization error is reported on the *instance*, which the caller
        # holds, and not on a document which has not been written yet, so
        # the path is a Java access path and not a JSON pointer.
        getter_path = f"{getter_name}()"

        # NOTE (mristin):
        # A verification error, in contrast, is reported with the JSON path.
        json_path = (
            numeric_place.prop.json_name
            if numeric_place.index is None
            else f"{numeric_place.prop.json_name}[{numeric_place.index}]"
        )

        if numeric_place.index is None:
            mutation = Stripped(f"instance.{setter_name}(value);")
            expected_path = getter_path
        elif numeric_place.in_list:
            # NOTE (mristin):
            # The value goes to the position indicated by the numeric place so
            # that a serializer which always reports the index 0 does not pass.
            items_joined = ", ".join(
                "value" if i == numeric_place.index else zero_literal
                for i in range(numeric_place.index + 1)
            )

            mutation = Stripped(
                f"instance.{setter_name}(Arrays.asList({items_joined}));"
            )
            expected_path = f"{getter_path}.get({numeric_place.index})"
        else:
            type_anno = numeric_place.prop.type_annotation
            assert isinstance(type_anno, intermediate.TupleTypeAnnotation), (
                f"Expected a tuple at the numeric place of "
                f"{numeric_place.cls.name}.{numeric_place.prop.name}, "
                f"but got: {type_anno}"
            )

            items_joined = ",\n".join(
                "value"
                if i == numeric_place.index
                else f"instance.{getter_name}().item{i + 1}()"
                for i in range(len(type_anno.items))
            )

            tuple_type = java_common.generate_type(type_anno)

            mutation = Stripped(
                f"""\
instance.{setter_name}(
{I}new {tuple_type}(
{II}{indent_but_first_line(items_joined, II)}));"""
            )

            # NOTE (mristin):
            # A tuple item is reported as an index, just as a list item is, so
            # the two paths coincide.
            expected_path = f"{getter_path}.get({numeric_place.index})"

        cls_name_java = java_naming.class_name(numeric_place.cls.name)
        cls_name_json = naming.json_model_type(numeric_place.cls.name)

        test_name = java_naming.method_name(
            Identifier(
                f"test_{numeric_place.cls.name}_{numeric_place.prop.name}"
                f"_serialization_{what}"
            )
        )

        result.append(
            Stripped(
                f"""\
@Test
public void {test_name}() throws IOException {{
{I}for ({value_type} value : new {value_type}[] {values_literal}) {{
{II}final {cls_name_java} instance =
{III}Jsonization.Deserialize.deserialize{cls_name_java}(
{IIII}loadTheFirstExpected({java_common.string_literal(cls_name_json)}));

{II}{indent_but_first_line(mutation, II)}

{II}try {{
{III}Jsonization.Serialize.toJsonObject(instance);
{III}fail(
{IIII}"Expected the serialization to fail at "
{IIIII}+ {java_common.string_literal(expected_path)}
{IIIII}+ ", but it succeeded");
{II}}} catch (Jsonization.SerializeException exception) {{
{III}assertEquals(
{IIII}{java_common.string_literal(expected_path)},
{IIII}exception.getPath().orElse(null));
{II}}}
{I}}}
}} // public void {test_name}"""
            )
        )

        if numeric_place.a_type is not intermediate.PrimitiveType.INT:
            continue

        # NOTE (mristin):
        # The verification has to refuse exactly the integers which the
        # serializations refuse, so that a verified instance can always be
        # serialized, to JSON and to XML alike.
        outside_test_name = java_naming.method_name(
            Identifier(
                f"test_{numeric_place.cls.name}_{numeric_place.prop.name}"
                f"_outside_the_safe_integer_range"
            )
        )

        result.append(
            Stripped(
                f"""\
@Test
public void {outside_test_name}() throws IOException, XMLStreamException {{
{I}for (long value : new long[] {{9007199254740992L, -9007199254740992L}}) {{
{II}final {cls_name_java} instance =
{III}Jsonization.Deserialize.deserialize{cls_name_java}(
{IIII}loadTheFirstExpected({java_common.string_literal(cls_name_json)}));

{II}{indent_but_first_line(mutation, II)}

{II}final String expected =
{III}"Expected an integer, but got " + value
{IIII}+ ", which is outside the safe integer range [-2^53 + 1, 2^53 - 1]";

{II}final List<String> errors = verificationErrors(instance);
{II}if (!errors.contains({java_common.string_literal(f"{json_path}: ")} + expected)) {{
{III}fail("Expected the verification error " + expected + ", but got: " + errors);
{II}}}

{II}assertEquals(expected, jsonSerializationFailure(instance));
{II}assertEquals(expected, xmlSerializationFailure(instance));
{I}}}
}} // public void {outside_test_name}"""
            )
        )

        bounds_test_name = java_naming.method_name(
            Identifier(
                f"test_{numeric_place.cls.name}_{numeric_place.prop.name}"
                f"_at_the_safe_integer_bounds"
            )
        )

        result.append(
            Stripped(
                f"""\
@Test
public void {bounds_test_name}() throws IOException, XMLStreamException {{
{I}for (long value : new long[] {{9007199254740991L, -9007199254740991L}}) {{
{II}final {cls_name_java} instance =
{III}Jsonization.Deserialize.deserialize{cls_name_java}(
{IIII}loadTheFirstExpected({java_common.string_literal(cls_name_json)}));

{II}{indent_but_first_line(mutation, II)}

{II}assertNoSafeIntegerError(instance);
{I}}}
}} // public void {bounds_test_name}"""
            )
        )

    return result


def _generate_json_able_property_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the tests that a JSON-able property has to hold safe integers.

    An integer is put into the JSON-able value of the property from outside,
    and the verification, the JSON serialization and the XML serialization all
    have to refuse it alike.
    """
    result: List[Stripped] = []

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = prop.type_annotation

            # NOTE (mristin):
            # We wrap the integer in an array or in an object with a plain key,
            # so that the tests also cover the path within a JSON-able value.
            # A constrained key would have to satisfy invariants which we do
            # not know here.
            build: Stripped
            json_path: str
            if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
                build = Stripped(
                    "final JsonNode node = "
                    "JsonNodeFactory.instance.arrayNode().add(value);"
                )
                json_path = f"{prop.json_name}[0]"
            elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
                build = Stripped(
                    "final ArrayNode node = "
                    "JsonNodeFactory.instance.arrayNode().add(value);"
                )
                json_path = f"{prop.json_name}[0]"
            elif (
                isinstance(type_anno, intermediate.JsonObjectTypeAnnotation)
                and intermediate.try_constrained_primitive(type_anno.key) is None
            ):
                build = Stripped(
                    "final ObjectNode node = "
                    'JsonNodeFactory.instance.objectNode().put("key", value);'
                )
                json_path = f'{prop.json_name}["key"]'
            else:
                continue

            cls_name_java = java_naming.class_name(cls.name)
            cls_name_json = naming.json_model_type(cls.name)
            setter_name = java_naming.method_name(Identifier(f"set_{prop.name}"))

            outside_test_name = java_naming.method_name(
                Identifier(
                    f"test_{cls.name}_{prop.name}_outside_the_safe_integer_range"
                )
            )

            result.append(
                Stripped(
                    f"""\
@Test
public void {outside_test_name}() throws IOException, XMLStreamException {{
{I}for (long value : new long[] {{9007199254740992L, -9007199254740992L}}) {{
{II}final {cls_name_java} instance =
{III}Jsonization.Deserialize.deserialize{cls_name_java}(
{IIII}loadTheFirstExpected({java_common.string_literal(cls_name_json)}));

{II}{build}
{II}instance.{setter_name}(node);

{II}final String expected =
{III}"Expected a JSON-able value, but got the integer " + value
{IIII}+ ", which is outside the safe integer range [-2^53 + 1, 2^53 - 1]";

{II}final List<String> errors = verificationErrors(instance);
{II}if (!errors.contains({java_common.string_literal(f"{json_path}: ")} + expected)) {{
{III}fail("Expected the verification error " + expected + ", but got: " + errors);
{II}}}

{II}assertEquals(expected, jsonSerializationFailure(instance));
{II}assertEquals(expected, xmlSerializationFailure(instance));
{I}}}
}} // public void {outside_test_name}"""
                )
            )

            bounds_test_name = java_naming.method_name(
                Identifier(f"test_{cls.name}_{prop.name}_at_the_safe_integer_bounds")
            )

            result.append(
                Stripped(
                    f"""\
@Test
public void {bounds_test_name}() throws IOException, XMLStreamException {{
{I}for (long value : new long[] {{9007199254740991L, -9007199254740991L}}) {{
{II}final {cls_name_java} instance =
{III}Jsonization.Deserialize.deserialize{cls_name_java}(
{IIII}loadTheFirstExpected({java_common.string_literal(cls_name_json)}));

{II}{build}
{II}instance.{setter_name}(node);

{II}assertNoSafeIntegerError(instance);
{I}}}
}} // public void {bounds_test_name}"""
                )
            )

    return result


def _generate_safe_integer_helpers() -> List[Stripped]:
    """
    Generate the helpers of the tests over the safe integer range.

    The helpers render what the verification and the two serializations
    report, so that a test can compare it against the expected message.
    """
    return [
        Stripped(
            f"""\
/**
 * Render the verification errors of {{@code instance}} as
 * {{@code "path: cause"}}.
 */
private static List<String> verificationErrors(IClass instance) {{
{I}final List<String> result = new ArrayList<>();
{I}for (Reporting.Error error : Verification.verify(instance)) {{
{II}result.add(
{III}Reporting.generateJsonPath(error.getPathSegments())
{IIII}+ ": " + error.getCause());
{I}}}
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Serialize {{@code instance}} to JSON, and give the reason why it failed,
 * or null if it did not.
 */
private static String jsonSerializationFailure(IClass instance) {{
{I}try {{
{II}Jsonization.Serialize.toJsonObject(instance);
{II}return null;
{I}}} catch (Jsonization.SerializeException exception) {{
{II}return exception.getReason().orElse(null);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Serialize {{@code instance}} to XML, and give the reason why it failed,
 * or null if it did not.
 */
private static String xmlSerializationFailure(IClass instance)
{I}throws XMLStreamException {{
{I}final XMLStreamWriter writer =
{II}XMLOutputFactory.newFactory().createXMLStreamWriter(new StringWriter());
{I}try {{
{II}Xmlization.Serialize.to(instance, writer);
{II}return null;
{I}}} catch (XmlCommon.SerializeException exception) {{
{II}return exception.getReason().orElse(null);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Assert that neither the verification nor the serializations refuse
 * an integer of {{@code instance}} as outside the safe integer range.
 */
private static void assertNoSafeIntegerError(IClass instance)
{I}throws XMLStreamException {{
{I}for (String error : verificationErrors(instance)) {{
{II}if (error.contains("outside the safe integer range")) {{
{III}fail("Expected no safe integer error, but got: " + error);
{II}}}
{I}}}

{I}assertNull(jsonSerializationFailure(instance));
{I}assertNull(xmlSerializationFailure(instance));
}}"""
        ),
    ]


def _generate_is_safe_integer_test() -> Stripped:
    """Generate the test of the predicates over the safe integer range."""
    return Stripped(
        f"""\
@Test
public void testIsSafeInteger() {{
{I}assertTrue(Verification.isSafeInteger(9007199254740991L));
{I}assertTrue(Verification.isSafeInteger(-9007199254740991L));
{I}assertFalse(Verification.isSafeInteger(9007199254740992L));
{I}assertFalse(Verification.isSafeInteger(-9007199254740992L));

{I}assertTrue(Verification.isSafeInteger(9007199254740991.0));
{I}assertTrue(Verification.isSafeInteger(-9007199254740991.0));
{I}assertFalse(Verification.isSafeInteger(9007199254740992.0));
{I}assertFalse(Verification.isSafeInteger(-9007199254740992.0));

{I}assertTrue(Verification.isSafeInteger(BigInteger.valueOf(9007199254740991L)));
{I}assertTrue(Verification.isSafeInteger(BigInteger.valueOf(-9007199254740991L)));
{I}assertFalse(Verification.isSafeInteger(BigInteger.valueOf(9007199254740992L)));
{I}assertFalse(Verification.isSafeInteger(BigInteger.valueOf(-9007199254740992L)));
{I}assertFalse(Verification.isSafeInteger(BigInteger.ONE.shiftLeft(64)));
{I}assertFalse(Verification.isSafeInteger(BigInteger.ONE.shiftLeft(64).negate()));
}} // public void testIsSafeInteger"""
    )


def _generate_load_the_first_expected() -> Stripped:
    """Generate the helper loading the first recorded JSON example of a class."""
    return Stripped(
        f"""\
private static JsonNode loadTheFirstExpected(String modelType) throws IOException {{
{I}final List<Path> paths =
{II}Common.findPaths(
{III}Paths.get(
{IIII}Common.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Expected",
{IIII}modelType),
{III}".json");

{I}if (paths.isEmpty()) {{
{II}fail("Expected at least one recorded example of " + modelType + ", but got none");
{I}}}

{I}return CommonJson.readFromFile(paths.get(0));
}}"""
    )


def _generate_json_value_safe_integer_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the tests that a JSON-able integer has to be a safe integer.

    The verification, the de-serialization and the serialization of
    a JSON-able value have to agree on the integers they refuse.
    """
    if not intermediate_uses.json_types(symbol_table):
        return []

    return [
        Stripped(
            f"""\
@Test
public void testJsonValueOutsideTheSafeIntegerRangeFails() {{
{I}final JsonNode[] nodes = new JsonNode[] {{
{II}JsonNodeFactory.instance.numberNode(9007199254740992L),
{II}JsonNodeFactory.instance.numberNode(-9007199254740992L),
{II}JsonNodeFactory.instance.numberNode(BigInteger.ONE.shiftLeft(64))
{I}}};

{I}for (JsonNode node : nodes) {{
{II}final String expected =
{III}"Expected a JSON-able value, but got the integer " + node
{IIII}+ ", which is outside the safe integer range [-2^53 + 1, 2^53 - 1]";

{II}final List<String> got = new ArrayList<>();
{II}Verification.verifyJsonValue(node).forEach(
{III}error -> got.add(error.getCause()));
{II}assertEquals(Arrays.asList(expected), got);

{II}try {{
{III}Jsonization.Deserialize.deserializeJsonValue(node);
{III}fail("Expected the de-serialization of " + node + " to fail, but it succeeded");
{II}}} catch (Jsonization.DeserializeException exception) {{
{III}assertEquals(expected, exception.getReason().orElse(null));
{II}}}

{II}try {{
{III}Jsonization.Serialize.jsonValueToJsonNode(node);
{III}fail("Expected the serialization of " + node + " to fail, but it succeeded");
{II}}} catch (Jsonization.SerializeException exception) {{
{III}assertEquals(expected, exception.getReason().orElse(null));
{II}}}
{I}}}
}} // public void testJsonValueOutsideTheSafeIntegerRangeFails"""
        ),
        Stripped(
            f"""\
@Test
public void testJsonValueAtTheSafeIntegerBoundsOk() {{
{I}for (long value : new long[] {{9007199254740991L, -9007199254740991L}}) {{
{II}final JsonNode node = JsonNodeFactory.instance.numberNode(value);

{II}assertEquals(0L, Verification.verifyJsonValue(node).count());

{II}assertEquals(node, Jsonization.Deserialize.deserializeJsonValue(node));

{II}assertEquals(node, Jsonization.Serialize.jsonValueToJsonNode(node));
{I}}}
}} // public void testJsonValueAtTheSafeIntegerBoundsOk"""
        ),
    ]


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the JSON de/serialization of concrete classes.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
private static void assertSerializeDeserializeEqualsOriginal(JsonNode originalNode, IClass instance, Path path)
{I}throws JsonProcessingException {{
{I}final ObjectMapper objectMapper = new ObjectMapper();

{I}JsonNode serialized = null;
{I}try {{
{II}serialized = Jsonization.Serialize.toJsonObject(instance);
{I}}} catch (Exception exception) {{
{II}fail("Expected no exception upon serialization of an instance " +
{III}"de-serialized from " + path + ", but got: " + exception);
{I}}}

{I}if (serialized == null) {{
{II}fail(
{III}"Unexpected null serialization of an instance from " + path);
{I}}}

assertEquals(objectMapper.readTree(originalNode.toString()), objectMapper.readTree(serialized.toString()));
}}"""
        ),
        Stripped(
            f"""\
private static void assertEqualsExpectedOrRerecordDeserializationException(
{I}Jsonization.DeserializeException exception,
{I}Path path) throws FileNotFoundException, IOException{{
{I}if (exception == null) {{
{II}fail("Expected a Jsonization exception when de-serializing " +
{II}path +
{II}", but got none.");
{I}}} else {{
{II}final Path exceptionPath = Paths.get(path + ".exception");
{II}final String got = exception.getMessage();
{II}if (Common.RECORD_MODE) {{
{III}Files.write(exceptionPath, got.getBytes(StandardCharsets.UTF_8));
{II}}} else {{
if (!Files.exists(exceptionPath)) {{
{I}throw new FileNotFoundException(
{II}"The file with the recorded errors does not exist: "
{III}+ exceptionPath
{III}+ "; maybe you want to set the environment variable "
{III}+ Common.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME);
}}
final String expected =
{I}Files.readAllLines(exceptionPath).stream().collect(Collectors.joining("\\n"));
assertEquals(
{I}expected,
{I}got,
{I}"The expected exception does not match the actual one for the file " + path);
{II}}}
{I}}}
}}"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_java = java_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}Ok() throws IOException {{
{I}final ObjectMapper objectMapper = new ObjectMapper();

{I}final Path searchPath = Paths.get(
{II}Common.TEST_DATA_DIR,
{II}"Json",
{II}"Expected",
{II}{java_common.string_literal(cls_name_json)});
{I}final List<Path> paths = Common.findPaths(searchPath, ".json");

{I}for (Path path : paths) {{
{II}final JsonNode node = objectMapper.readTree(path.toFile());
{II}final {cls_name_java} instance = Jsonization.Deserialize.deserialize{cls_name_java}(node);

{II}final Iterable<Reporting.Error> errorIter = Verification.verify(instance);
{II}final List<Reporting.Error> errors = Common.asList(errorIter);
{II}Common.assertNoVerificationErrors(errors, path);
{I}}}
}} // public void test{cls_name_java}Ok"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}DeserializationFromNonObjectFail() throws IOException {{
{I}final JsonNode node = JsonNodeFactory.instance.textNode("INVALID");

{I}Jsonization.DeserializeException exception = null;
{I}try {{
{II}final {cls_name_java} unused = Jsonization.Deserialize.deserialize{cls_name_java}(node);
{I}}} catch (Jsonization.DeserializeException observedException) {{
{II}exception = observedException;
{I}}}

{I}assert exception != null : "Expected an exception, but got none";
{I}assert exception.getMessage().startsWith("Expected a JsonObject, but got ") :
{II}"Unexpected exception message: " + exception.getMessage();
}} // public void test{cls_name_java}DeserializationFromNonObjectFail"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}DeserializationFail() throws IOException {{
{I}for (Path causeDir :
{II}Common.findDirs(
{III}Paths.get(
{IIII}Common.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Unexpected",
{IIII}"Unserializable"))) {{
{II}final Path clsDir = causeDir.resolve({java_common.string_literal(cls_name_json)});

{II}if (!Files.exists(clsDir)) {{
{III}// No examples of {cls_name_java} for the failure cause.
{III}continue;
{II}}}

{II}final List<Path> paths = Common.findPaths(clsDir, ".json");
{II}for (Path path : paths) {{
{III}final JsonNode node = CommonJson.readFromFile(path);

{III}Jsonization.DeserializeException exception = null;
{III}try {{
{IIII}final {cls_name_java} var = Jsonization.Deserialize.deserialize{cls_name_java}(node);
{III}}} catch (Jsonization.DeserializeException observedException) {{
{IIII}exception = observedException;
{III}}}

{III}assertEqualsExpectedOrRerecordDeserializationException(
{IIII}exception, path);
{II}}}
{I}}}
}} // public void test{cls_name_java}DeserializationFail"""
            )
        )

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}VerificationFail() throws IOException {{
{I}for (Path causeDir :
{II}Common.findDirs(
{III}Paths.get(
{IIII}Common.TEST_DATA_DIR,
{IIII}"Json",
{IIII}"Unexpected",
{IIII}"Invalid"))) {{
{II}final Path clsDir = causeDir.resolve({java_common.string_literal(cls_name_json)});

{II}if (!Files.exists(clsDir)) {{
{III}// No examples of {cls_name_java} for the failure cause.
{III}continue;
{II}}}

{II}final List<Path> paths = Common.findPaths(clsDir, ".json");
{II}for (Path path : paths) {{
{III}final JsonNode node = CommonJson.readFromFile(path);

{III}final {cls_name_java} instance = Jsonization.Deserialize.deserialize{cls_name_java}(node);

{III}final Iterable<Reporting.Error> errorIter = Verification.verify(instance);
{III}final List<Reporting.Error> errors = Common.asList(errorIter);
{III}Common.assertEqualsExpectedOrRerecordVerificationErrors(errors, path);
{II}}}
{I}}}
}} // public void test{cls_name_java}VerificationFail"""
            )
        )

    serialization_failure_tests = _generate_serialization_failure_tests(symbol_table)

    json_able_property_tests = _generate_json_able_property_tests(symbol_table)

    if len(serialization_failure_tests) > 0 or len(json_able_property_tests) > 0:
        blocks.append(_generate_load_the_first_expected())

    # NOTE (mristin):
    # The helpers are only called by the tests over the integers, which are
    # generated whenever an instance or a JSON-able value can hold one.
    if intermediate_uses.safe_integer_checks(symbol_table):
        blocks.extend(_generate_safe_integer_helpers())
        blocks.append(_generate_is_safe_integer_test())

    blocks.extend(serialization_failure_tests)

    blocks.extend(json_able_property_tests)

    blocks.extend(_generate_json_value_safe_integer_tests(symbol_table))

    # NOTE (mristin):
    # Only the tests of the serialization failures name a tuple, an interface
    # or an enumeration of the meta-model, as they have to rebuild the value
    # they corrupt.
    extra_imports = (
        f"""\
import {package}.common.*;
import {package}.types.enums.*;
import {package}.types.model.*;
"""
        if len(serialization_failure_tests) > 0
        else ""
    )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestJsonizationOfConcreteClasses.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import {package}.jsonization.Jsonization;
import {package}.reporting.Reporting;
import {package}.types.impl.*;
import {package}.types.model.IClass;
{extra_imports}\
import {package}.verification.Verification;
import {package}.xmlcommon.XmlCommon;
import {package}.xmlization.Xmlization;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.StringWriter;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamWriter;
import org.junit.jupiter.api.Test;

public class TestJsonizationOfConcreteClasses {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestJsonizationOfConcreteClasses

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
