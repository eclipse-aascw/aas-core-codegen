"""Generate code to test the JSON de/serialization of concrete classes."""

from typing import List

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _tuple_items(
    numeric_place: intermediate.NumericPlace,
) -> "List[intermediate.TypeAnnotationUnion]":
    """Give out the items of the tuple at the ``numeric_place``."""
    type_anno = numeric_place.prop.type_annotation
    assert isinstance(type_anno, intermediate.TupleTypeAnnotation), (
        f"Expected a tuple at the numeric place of "
        f"{numeric_place.cls.name}.{numeric_place.prop.name}, but got: {type_anno}"
    )
    return list(type_anno.items)


def _generate_serialization_failure_tests(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the tests that a number unrepresentable in JSON is refused."""
    result = []  # type: List[Stripped]

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

        json_name = numeric_place.prop.json_name

        if numeric_place.index is None:
            mutation = Stripped(f"instance.{setter_name}(value);")
            expected_path = f"{json_name}"
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
            expected_path = f"{json_name}[{numeric_place.index}]"
        else:
            items_joined = ",\n".join(
                "value"
                if i == numeric_place.index
                else f"instance.{getter_name}().item{i + 1}()"
                for i in range(len(_tuple_items(numeric_place)))
            )

            tuple_type = java_common.generate_type(numeric_place.prop.type_annotation)

            mutation = Stripped(
                f"""\
instance.{setter_name}(
{I}new {tuple_type}(
{II}{indent_but_first_line(items_joined, II)}));"""
            )
            expected_path = f"{json_name}[{numeric_place.index}]"

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

    if len(result) > 0:
        result.insert(
            0,
            Stripped(
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
            ),
        )

    return result


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the JSON de/serialization of concrete classes.
    """
    blocks = [
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
    ]  # type: List[Stripped]

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

    blocks.extend(serialization_failure_tests)

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
import static org.junit.jupiter.api.Assertions.fail;

import {package}.jsonization.Jsonization;
import {package}.reporting.Reporting;
import {package}.types.impl.*;
import {package}.types.model.IClass;
{extra_imports}\
import {package}.verification.Verification;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
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
