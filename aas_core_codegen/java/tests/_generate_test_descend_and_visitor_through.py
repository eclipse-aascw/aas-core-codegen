"""Generate code to test the ``Descend`` methods and ``VisitorThrough``."""

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
    Generate code to test the ``Descend`` methods and ``VisitorThrough``.
    """
    blocks: List[str] = [
        Stripped(
            f"""\
private class _TracingVisitorThrough extends VisitorThrough {{
{I}public final List<String> log = new ArrayList<>();

{I}@Override
{I}public void visit(IClass that) {{
{II}log.add(Common.trace(that));
{II}super.visit(that);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private void assertDescendAndVisitorThroughSame(IClass instance)
{{
{I}final List<String> logFromDescend = new ArrayList<>();

{I}for (IClass subInstance : instance.descend()) {{
{II}logFromDescend.add(Common.trace(subInstance));
{I}}}

{I}final _TracingVisitorThrough visitor = new _TracingVisitorThrough();
{I}visitor.visit(instance);
{I}final List<String> traceFromVisitor = visitor.log;

{I}assertFalse(traceFromVisitor.isEmpty());

{I}assertEquals(Common.trace(instance), traceFromVisitor.get(0));

{I}traceFromVisitor.remove(0);

{I}assertTrue(traceFromVisitor.equals(logFromDescend));
}}"""
        ),
        Stripped(
            f"""\
private void compareOrRerecordTrace(IClass instance, Path expectedPath) throws IOException {{
{I}final StringBuilder stringBuilder = new StringBuilder();
{I}for (IClass descendant : instance.descend()) {{
{II}stringBuilder.append(Common.trace(descendant));
{I}}}

{I}final String got = stringBuilder.toString();
{I}if (Common.RECORD_MODE) {{
{II}Files.createDirectories(expectedPath.getParent());
{II}Files.write(expectedPath, got.getBytes());
{I}}} else {{
{II}if (!Files.exists(expectedPath)) {{
{III}throw new FileNotFoundException(
{IIIII}"The file with the recorded value does not exist: " + expectedPath);
{II}}}
{II}final String expected =
{IIII}Files.readAllLines(expectedPath).stream().collect(Collectors.joining("\\n"));
{II}assertEquals(expected.replace("\\n", ""), got.replace("\\n", ""));
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
public void testDescendOf{cls_name_java}() throws IOException {{
{I}final {cls_name_java} instance = CommonJsonization.loadMaximal{cls_name_java}();

{I}compareOrRerecordTrace(
{II}instance,
{II}Paths.get(
{III}Common.TEST_DATA_DIR,
{III}"Descend",
{III}{java_common.string_literal(cls_name_json)},
{III}"maximal.json.trace"));
}} // public void testDescendOf{cls_name_java}

@Test
public void testDescendAgainstVisitorThroughFor{cls_name_java}() throws IOException {{
{I}{cls_name_java} instance = (
{II}CommonJsonization.loadMaximal{cls_name_java}());

{I}assertDescendAndVisitorThroughSame(instance);
}} // public void testDescendAgainstVisitorThroughFor{cls_name_java}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestDescendAndVisitorThrough.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.*;

import {package}.types.impl.*;
import {package}.types.model.IClass;
import {package}.visitation.VisitorThrough;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

public class TestDescendAndVisitorThrough {{
{I}{indent_but_first_line(blocks_joined, II)}
}} // class TestDescendAndVisitorThrough

// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
