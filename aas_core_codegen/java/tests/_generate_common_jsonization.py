"""Generate the Java code for shared JSON functionality across unit tests."""

from typing import List

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import INDENT as I, INDENT2 as II


def generate(
    package: java_common.PackageIdentifier, symbol_table: intermediate.SymbolTable
) -> List[java_common.JavaFile]:
    """
    Generate the Java code for shared JSON functionality across unit tests.
    """
    blocks: List[str] = []

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_java = java_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
public static {cls_name_java} loadMaximal{cls_name_java}() throws IOException {{
{I}final Path path = Paths.get(
{II}Common.TEST_DATA_DIR,
{II}"Json",
{II}"Expected",
{II}{java_common.string_literal(cls_name_json)},
{II}"maximal.json");

{I}final JsonNode node = CommonJson.readFromFile(path);

{I}return Jsonization.Deserialize.deserialize{cls_name_java}(node);
}} // public static {cls_name_java} loadMaximal{cls_name_java}

public static {cls_name_java} loadMinimal{cls_name_java}() throws IOException {{
{I}final Path path = Paths.get(
{II}Common.TEST_DATA_DIR,
{II}"Json",
{II}"Expected",
{II}{java_common.string_literal(cls_name_json)},
{II}"minimal.json");

{I}final JsonNode node = CommonJson.readFromFile(path);

{I}return Jsonization.Deserialize.deserialize{cls_name_java}(node);
}} // public static {cls_name_java} loadMinimal{cls_name_java}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "CommonJsonization.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import {package}.jsonization.Jsonization;
import {package}.types.impl.*;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Provide methods to load instances from JSON test data.
 */
public final class CommonJsonization {{
{I}{indent_but_first_line(blocks_joined, I)}
}} // class CommonJsonization

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
