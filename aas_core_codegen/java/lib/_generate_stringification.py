"""Generate the code for de/serialization of enumerations."""

import io
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    indent_but_first_line,
    Error,
    Stripped,
    Identifier,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
)


def _generate_enum_to_and_from_string(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the methods for de/serializing enumeration from/to a string."""
    blocks = []  # type: List[Stripped]

    name = java_naming.enum_name(enumeration.name)

    text_name = java_naming.method_name(Identifier("literal_text"))

    # NOTE (mristin):
    # There is no map from the literals to their strings. A literal carries
    # its own text (see the ``IEnum`` interface in the types), so the two
    # methods below only have to hand it out. The other direction does need
    # a map, as a string carries nothing.

    # region To-string-method

    to_str_name = java_naming.method_name(Identifier("to_string"))

    to_str_writer = io.StringIO()
    to_str_writer.write(
        f"""\
/**
 * Retrieve the string representation of {{@code that}}.
 *
 * <p>If {{@code that}} is not a valid literal, return {{@code Optional#empty()}}.
 */
public static Optional<String> {to_str_name}({name} that)
{{
{I}return (that == null)
{II}? Optional.empty()
{II}: Optional.of(that.{text_name}());
}}"""
    )

    blocks.append(Stripped(to_str_writer.getvalue()))

    # endregion

    # region Must-to-string-method

    must_to_str_name = java_naming.method_name(Identifier("must_to_string"))

    blocks.append(
        Stripped(
            f"""\
/**
 * Retrieve the string representation of {{@code that}}.
 *
 * @throws IllegalArgumentException if {{@code that}} is not a valid literal
 */
public static String {must_to_str_name}({name} that)
{{
{I}if (that == null) {{
{II}throw new IllegalArgumentException("Invalid literal of {name}: " + that);
{I}}}
{I}return that.{text_name}();
}}"""
        )
    )

    # endregion

    # region From-string-map

    string_to_enum_blocks = []  # type: List[Stripped]

    for literal in enumeration.literals:
        literal_name = java_naming.enum_literal_name(literal.name)

        literal_string = java_common.string_literal(literal.value)

        string_to_enum_blocks.append(
            Stripped(f"""temp.put({literal_string}, {name}.{literal_name});""")
        )

    string_to_enum_mapping = "\n".join(string_to_enum_blocks)

    from_str_map_name = java_naming.private_property_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    from_str_map = Stripped(
        f"""\
private static final Map<String, {name}> {from_str_map_name};
static {{
{I}final Map<String, {name}> temp = new HashMap<>();

{I}{indent_but_first_line(string_to_enum_mapping, I)}

{I}if (!temp.values().containsAll(Arrays.asList({name}.values()))) {{
{II}throw new IllegalStateException("Unmapped {name}");
{I}}}

{I}{from_str_map_name} = Collections.unmodifiableMap(temp);
}}"""
    )

    blocks.append(from_str_map)

    # endregion

    # region From-string-method

    from_str_name = java_naming.method_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    from_str_writer = io.StringIO()
    from_str_writer.write(
        f"""\
/**
 * Parse the string representation of {{@link {name}}}.
 *
 * <p>If {{@code text}} is not a valid string representation
 * of a literal of {{@link {name}}},
 * return {{@code Optional#empty()}}.
 */
public static Optional<{name}> {from_str_name}(String text)
{{
{I}{name} value = {from_str_name}.get(text);
{I}if (value == null) {{
{II}return Optional.empty();
{I}}} else {{
{II}return Optional.of(value);
{I}}}
}}"""
    )

    blocks.append(Stripped(from_str_writer.getvalue()))

    # endregion

    return Stripped("\n\n".join(blocks))


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate the code for de/serialization of enumerations.
    """
    stringification_blocks = []  # type: List[Stripped]

    for enum in symbol_table.enumerations:
        stringification_blocks.append(
            _generate_enum_to_and_from_string(enumeration=enum)
        )

    stringification_code = Stripped("\n\n".join(stringification_blocks))

    code = Stripped(
        f"""\
{java_common.WARNING}

package {package}.stringification;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import {package}.types.enums.*;

public class Stringification {{
{I}{indent_but_first_line(stringification_code, I)}
}}

{java_common.WARNING}"""
    )

    return [java_common.JavaFile("Stringification.java", f"{code}\n")], None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
