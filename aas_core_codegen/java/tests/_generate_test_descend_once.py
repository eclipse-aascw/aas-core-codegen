"""Generate code to test the ``DescendOnce`` methods."""

from typing import List

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test the ``DescendOnce`` methods.
    """
    blocks: List[str] = [
        Stripped(
            f"""\
private static void compareOrRerecordTrace(IClass instance, Path expectedPath)
{I}throws IOException, FileNotFoundException {{
{I}final StringBuilder stringBuilder = new StringBuilder();
{I}for (IClass descendant : instance.descendOnce()) {{
{II}stringBuilder.append(Common.trace(descendant));
{I}}}

{I}final String got = stringBuilder.toString();

{I}if (Common.RECORD_MODE) {{
{II}Files.createDirectories(expectedPath.getParent());
{II}Files.write(expectedPath, got.getBytes());
{I}}} else {{
{II}if (!Files.exists(expectedPath)) {{
{III}throw new FileNotFoundException(
{IIII}"The file with the recorded trace does not exist: "
{IIIII}+ expectedPath
{IIIII}+ "; maybe you want to set the environment variable "
{IIIII}+ Common.RECORD_MODE_ENVIRONMENT_VARIABLE_NAME);
{II}}}
{II}final String expected =
{III}Files.readAllLines(expectedPath).stream().collect(Collectors.joining("\\n"));
{II}assertEquals(expected.replace("\\n", ""), got.replace("\\n", ""));
{I}}}
}}"""
        )
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name_java = java_naming.class_name(concrete_cls.name)
        cls_name_json = naming.json_model_type(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name_java}() throws IOException {{
{I}{cls_name_java} instance = CommonJsonization.loadMaximal{cls_name_java}();

{I}compareOrRerecordTrace(
{II}instance,
{II}Paths.get(
{III}Common.TEST_DATA_DIR,
{III}"DescendOnce",
{III}{java_common.string_literal(cls_name_json)},
{III}"maximal.json.trace"));
}} // public void test{cls_name_java}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestDescendOnce.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.assertEquals;

import {package}.types.impl.*;
import {package}.types.model.IClass;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

public class TestDescendOnce {{
{I}{indent_but_first_line(blocks_joined, I)}
}}  // class TestDescendOnce

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
