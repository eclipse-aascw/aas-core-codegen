"""Generate code to test the ``XOrDefault`` methods."""

from typing import List, Optional

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the ``XOrDefault`` methods.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
private static void compareOrRerecordValue(Object value, Path expectedPath) throws IOException {{
{I}final ObjectMapper objectMapper = new ObjectMapper();
{I}JsonNode got = CommonJson.toJson(value);

{I}if (Common.RECORD_MODE) {{
{II}Files.createDirectories(expectedPath.getParent());
{II}Files.write(expectedPath, got.toString().getBytes());
{I}}}
{I}else
{I}{{
{II}if (!Files.exists(expectedPath)) {{
{III}throw new FileNotFoundException(
{IIII}"The file with the recorded value does not exist: " + expectedPath + "; " +
{IIII}"maybe you want to set the environment variable " +
{IIII}Common.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME + "?");
{II}}}

{II}final JsonNode expected = objectMapper.readTree(expectedPath.toFile());
{II}assertEquals(objectMapper.readTree(expected.toString()), objectMapper.readTree(got.toString()));
{I}}}
}}"""
        )
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_java = java_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        x_or_default_methods: List[intermediate.MethodUnion] = []
        for method in concrete_cls.methods:
            if (
                method.name.endswith("_or_default")
                and method.visibility is intermediate.Visibility.PUBLIC
            ):
                x_or_default_methods.append(method)

        for method in x_or_default_methods:
            method_name_java = java_naming.method_name(method.name)
            method_name_capitalized_java = (
                method_name_java[0].upper() + method_name_java[1:]
            )

            result_enum: Optional[intermediate.Enumeration] = None
            assert method.returns is not None, (
                f"Expected all X_or_default to return something, "
                f"but got None for {concrete_cls.name}.{method.name}"
            )

            if isinstance(
                method.returns, intermediate.OurTypeAnnotation
            ) and isinstance(method.returns.our_type, intermediate.Enumeration):
                result_enum = method.returns.our_type

            if result_enum is None:
                value_assignment_snippet = Stripped(
                    f"final Object value = instance.{method_name_java}();"
                )
            else:
                value_type_name_java = java_naming.enum_name(result_enum.name)
                value_assignment_snippet = Stripped(
                    f"""\
final {value_type_name_java} enumValue = instance.{method_name_java}();
if (enumValue == null) {{
{I}throw new IllegalStateException("Failed to stringify the enum");
}}

final Optional<String> valueOptional = Stringification.toString(enumValue);
assertEquals(true, valueOptional.isPresent());
final String value = valueOptional.get();"""
                )

            # noinspection SpellCheckingInspection
            blocks.append(
                Stripped(
                    f"""\
@Test
public void test{cls_name_java}{method_name_capitalized_java}NonDefault()
{I} throws IOException {{
{I}{cls_name_java} instance = CommonJsonization.loadMaximal{cls_name_java}();

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}compareOrRerecordValue(
{II}value,
{II}Paths.get(
{III}Common.TEST_DATA_DIR,
{III}"XOrDefault",
{III}{java_common.string_literal(cls_name_json)},
{III}"{method_name_java}.non-default.json"));
}} // public void test{cls_name_java}{method_name_java}NonDefault

@Test
public void test{cls_name_java}{method_name_java}Default()
{I} throws IOException {{
{I}{cls_name_java} instance = CommonJsonization.loadMinimal{cls_name_java}();

{I}{indent_but_first_line(value_assignment_snippet, I)}

{I}compareOrRerecordValue(
{II}value,
{II}Paths.get(
{III}Common.TEST_DATA_DIR,
{III}"XOrDefault",
{III}{java_common.string_literal(cls_name_json)},
{III}"{method_name_java}.default.json"));
}} // public void test{cls_name_java}{method_name_java}Default"""
                )
            )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestXOrDefault.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.reporting.*;
import {package}.stringification.Stringification;
import {package}.types.enums.*;
import {package}.types.impl.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Optional;
import org.junit.jupiter.api.Test;

public class TestXOrDefault {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class TestXOrDefault

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
