"""Generate code to test enhancing the model instances."""

from typing import List

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, indent_but_first_line
from aas_core_codegen.java import common as java_common, naming as java_naming
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def generate(
    package: java_common.PackageIdentifier,
    symbol_table: intermediate.SymbolTable,
) -> List[java_common.JavaFile]:
    """
    Generate code to test enhancing the model instances.
    """
    blocks: List[Stripped] = [
        Stripped(
            f"""\
public static class _Enhancement {{
{I}public final long someCustomId;

{I}public _Enhancement(long someCustomId) {{
{II}this.someCustomId = someCustomId;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
private Enhancer<_Enhancement> createEnhancer() {{
{I}AtomicLong lastCustomId = new AtomicLong();

{I}Function<IClass, Optional<_Enhancement>> enhancementFactory =
{II}iClass -> Optional.of(new _Enhancement(lastCustomId.incrementAndGet()));

{I}return new Enhancer<>(enhancementFactory);
}}"""
        ),
    ]

    for concrete_cls in symbol_table.concrete_classes:
        cls_name = java_naming.class_name(concrete_cls.name)

        blocks.append(
            Stripped(
                f"""\
@Test
public void test{cls_name}() throws IOException {{
{I}final {cls_name} instance = CommonJsonization.loadMaximal{cls_name}();

{I}final Enhancer<_Enhancement> enhancer = createEnhancer();

{I}assert !enhancer.unwrap(instance).isPresent();

{I}final IClass wrapped = enhancer.wrap(instance);
{I}assertNotNull(wrapped);

{I}final Set<Long> idSet = new HashSet<>();
{I}idSet.add(enhancer.mustUnwrap(wrapped).someCustomId);
{I}wrapped
{II}.descend()
{II}.forEach(descendant -> idSet.add(enhancer.mustUnwrap(descendant).someCustomId));

{I}assertFalse(enhancer.unwrap(instance).isPresent());
{I}assertNotNull(wrapped);
{I}assertEquals(
{II}1L,
{II}idSet.stream()
{III}.min(Comparator.comparing(Long::valueOf))
{III}.orElseThrow(() -> new IllegalStateException("Missing min value for wrapped.")));
{I}assertEquals(
{II}idSet.size(),
{II}idSet.stream()
{III}.max(Comparator.comparing(Long::valueOf))
{III}.orElseThrow(() -> new IllegalStateException("Missing max value for wrapped.")));
}} // public void test{cls_name}"""
            )
        )

    blocks_joined = "\n\n".join(blocks)

    return [
        java_common.JavaFile(
            "TestEnhancing.java",
            f"""\
{java_common.WARNING}

package {package}.tests;

import static org.junit.jupiter.api.Assertions.*;

import {package}.enhancing.Enhancer;
import {package}.types.impl.*;
import {package}.types.model.IClass;
import java.io.IOException;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

public class TestEnhancing {{
{I}{indent_but_first_line(blocks_joined, I)}
}}  // class TestEnhancing
// package {package}.tests

{java_common.WARNING}
""",
        )
    ]


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
