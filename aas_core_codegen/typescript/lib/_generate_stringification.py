"""Generate code for string de/serialization of enumerations."""

import io
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import Error, Stripped, Identifier, indent_but_first_line
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen import naming


def _generate_model_type_from_string(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the function to de-serialize model type from a string."""
    model_type_enum = typescript_naming.enum_name(Identifier("Model_type"))

    keys_values = []  # type: List[Stripped]
    for concrete_cls in symbol_table.concrete_classes:
        json_model_type = naming.json_model_type(concrete_cls.name)
        model_type_literal = typescript_naming.enum_literal_name(concrete_cls.name)

        assert json_model_type == model_type_literal, (
            f"Expected the JSON model type for class {concrete_cls.name!r}, "
            f"{json_model_type!r}, to equal the literal in the enumeration "
            f"{model_type_enum!r}, but it does not. "
            f"The literal is: {model_type_literal!r}. This will make it very confusing "
            f"for the user if the model type in JSON and in TypeScript differ. "
            f"Please contact the developers and re-evaluate whether it makes sense "
            f"to change the naming of the TypeScript enumeration literals."
        )

        json_model_type_literal = typescript_common.string_literal(json_model_type)

        keys_values.append(
            Stripped(
                f"""\
[
{I}{json_model_type_literal},
{I}AasTypes.{model_type_enum}.{model_type_literal}
]"""
            )
        )

    map_name = typescript_naming.constant_name(Identifier("model_type_from_string"))
    keys_values_joined = ",\n".join(keys_values)

    from_string = typescript_naming.function_name(Identifier("model_type_from_string"))

    return [
        Stripped(
            f"""\
const {map_name} = new Map<string, AasTypes.{model_type_enum}>([
{I}{indent_but_first_line(keys_values_joined, I)}
]);"""
        ),
        Stripped(
            f"""\
/**
 * Parse `text` as a string representation of {{@link types!{model_type_enum}}}.
 *
 * @param text - string representation of {{@link types!{model_type_enum}}}
 * @returns literal of {{@link types!{model_type_enum}}}, if valid, and `null` otherwise
 */
export function {from_string}(
{I}text: string
): AasTypes.{model_type_enum} | null {{
{I}const result = {map_name}.get(text);
{I}return result !== undefined ? result : null;
}}"""
        ),
    ]


def _generate_model_type_to_string(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the function to serialize a runtime model type to a string."""
    model_type_enum = typescript_naming.enum_name(Identifier("Model_type"))

    texts = []  # type: List[Stripped]
    for i, concrete_cls in enumerate(symbol_table.concrete_classes):
        json_model_type = naming.json_model_type(concrete_cls.name)
        model_type_literal = typescript_naming.enum_literal_name(concrete_cls.name)

        assert json_model_type == model_type_literal, (
            f"Expected the JSON model type for class {concrete_cls.name!r}, "
            f"{json_model_type!r}, to equal the literal in the enumeration "
            f"{model_type_enum!r}, but it does not. "
            f"The literal is: {model_type_literal!r}. This will make it very confusing "
            f"for the user if the model type in JSON and in TypeScript differ. "
            f"Please contact the developers and re-evaluate whether it makes sense "
            f"to change the naming of the TypeScript enumeration literals."
        )

        json_model_type_literal = typescript_common.string_literal(json_model_type)

        comma = "," if i < len(symbol_table.concrete_classes) - 1 else ""

        texts.append(Stripped(f"{json_model_type_literal}{comma}"))

    array_name = typescript_naming.constant_name(Identifier("model_type_to_string"))
    texts_joined = "\n".join(texts)

    to_string = typescript_naming.function_name(Identifier("model_type_to_string"))
    must_to_string = typescript_naming.function_name(
        Identifier("must_model_type_to_string")
    )

    return [
        Stripped(
            f"""\
// NOTE (mristin):
// The literals of {model_type_enum} are consecutive integers starting at 0,
// so we index into an array instead of looking the text up in a map.
const {array_name}: readonly string[] = [
{I}{indent_but_first_line(texts_joined, I)}
];"""
        ),
        Stripped(
            f"""\
/**
 * Translate {{@link types!{model_type_enum}}} to a string.
 *
 * @param value - to be stringified
 * @returns string representation of {{@link types!{model_type_enum}}},
 * if `value` valid, and `null` otherwise
 */
export function {to_string}(
{I}value: AasTypes.{model_type_enum}
): string | null {{
{I}const result = {array_name}[value];
{I}return result !== undefined ? result : null;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Translate {{@link types!{model_type_enum}}} to a string.
 *
 * @param value - to be stringified
 * @returns string representation of {{@link types!{model_type_enum}}}
 * @throws
 * {{@link https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error|Error}}
 * if the `value` is invalid
 */
export function {must_to_string}(
{I}value: AasTypes.{model_type_enum}
): string {{
{I}const result = {array_name}[value];
{I}if (result === undefined) {{
{II}throw new Error(
{III}`Invalid literal of {model_type_enum}: ${{value}}`
{II});
{I}}}
{I}return result;
}}"""
        ),
    ]


def _generate_enum_from_string(enumeration: intermediate.Enumeration) -> Stripped:
    """Generate the functions for de-serializing enumeration from strings."""
    blocks = []  # type: List[Stripped]

    name = typescript_naming.enum_name(enumeration.name)

    # region From-string-map

    items = []  # type: List[str]
    for literal in enumeration.literals:
        literal_name = typescript_naming.enum_literal_name(literal.name)
        literal_value = typescript_common.string_literal(literal.value)

        items.append(f"[{literal_value}, AasTypes.{name}.{literal_name}]")

    from_str_map_name = typescript_naming.constant_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    items_joined = ",\n".join(items)

    blocks.append(
        Stripped(
            f"""\
const {from_str_map_name} = new Map<string, AasTypes.{name}>([
{I}{indent_but_first_line(items_joined, I)}
]);"""
        )
    )

    # endregion

    # region From-string-function

    from_str_name = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Parse `text` as a string representation of {{@link types!{name}}}.
 *
 * @param text - string representation of {{@link types!{name}}}
 * @returns literal of {{@link types!{name}}}, if valid, and `null` otherwise
 */
export function {from_str_name}(
{I}text: string
): AasTypes.{name} | null {{
{I}const result = {from_str_map_name}.get(text);
{I}return result !== undefined ? result : null;
}}"""
        )
    )

    # endregion

    return Stripped("\n\n".join(blocks))


def _generate_enum_to_string(enumeration: intermediate.Enumeration) -> Stripped:
    """Generate the functions for serializing an enumeration literal to a string."""
    blocks = []  # type: List[Stripped]

    name = typescript_naming.enum_name(enumeration.name)

    # region To-string-array

    items = []  # type: List[str]
    for i, literal in enumerate(enumeration.literals):
        literal_name = typescript_naming.enum_literal_name(literal.name)
        literal_value = typescript_common.string_literal(literal.value)

        comma = "," if i < len(enumeration.literals) - 1 else ""

        # NOTE (mristin):
        # We spell out the name of the literal only where the text does not already
        # give it away, so that the reader can check that the array and
        # the enumeration line up.
        comment = f" // {literal_name}" if literal.value != literal_name else ""

        items.append(f"{literal_value}{comma}{comment}")

    to_str_array_name = typescript_naming.constant_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    if len(items) == 0:
        blocks.append(Stripped(f"const {to_str_array_name}: readonly string[] = [];"))
    else:
        items_joined = "\n".join(items)

        blocks.append(
            Stripped(
                f"""\
// NOTE (mristin):
// The literals of {name} are consecutive integers starting at 0,
// so we index into an array instead of looking the text up in a map.
const {to_str_array_name}: readonly string[] = [
{I}{indent_but_first_line(items_joined, I)}
];"""
            )
        )

    # endregion

    # region To-string-function

    to_str_name = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Translate {{@link types!{name}}} to a string.
 *
 * @param value - to be stringified
 * @returns string representation of {{@link types!{name}}}, if `value` valid, and `null` otherwise
 */
export function {to_str_name}(
{I}value: AasTypes.{name}
): string | null {{
{I}const result = {to_str_array_name}[value];
{I}return result !== undefined ? result : null;
}}"""
        )
    )

    must_to_str_name = typescript_naming.function_name(
        Identifier(f"must_{enumeration.name}_to_string")
    )

    blocks.append(
        Stripped(
            f"""\
/**
 * Translate {{@link types!{name}}} to a string.
 *
 * @param value - to be stringified
 * @returns string representation of {{@link types!{name}}}
 * @throws
 * {{@link https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error|Error}}
 * if the `value` is invalid
 */
export function {must_to_str_name}(
{I}value: AasTypes.{name}
): string {{
{I}const result = {to_str_array_name}[value];
{I}if (result === undefined) {{
{II}throw new Error(
{III}`Invalid literal of {name}: ${{value}}`
{II});
{I}}}
{I}return result;
}}"""
        )
    )

    # endregion

    return Stripped("\n\n".join(blocks))


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for string de/serialization of enumerations."""
    blocks = [
        Stripped(
            """\
/**
 * De/serialize enumerations from and to string representations.
 */"""
        ),
        typescript_common.WARNING,
        Stripped('import * as AasTypes from "./types";'),
        *_generate_model_type_from_string(symbol_table=symbol_table),
        *_generate_model_type_to_string(symbol_table=symbol_table),
    ]

    for enum in symbol_table.enumerations:
        blocks.append(_generate_enum_from_string(enumeration=enum))
        blocks.append(_generate_enum_to_string(enumeration=enum))

    blocks.append(typescript_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
