"""Provide functions shared among different TypeScript code generation modules."""
import io
import math
import re
from typing import List, Tuple, Optional, Union

from icontract import require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, assert_never, Identifier
from aas_core_codegen.typescript import naming as typescript_naming


def boolean_literal(value: bool) -> Stripped:
    """Generate the boolean literal corresponding to the ``value``."""
    return Stripped("true") if value else Stripped("false")


def representable_as_number(value: int) -> bool:
    """Check that the ``value`` can be represented as a double-precision float."""
    return float(value) == value


@require(lambda value: not isinstance(value, int) or representable_as_number(value))
def numeric_literal(value: Union[int, float]) -> Stripped:
    """Generate the numeric literal corresponding to the ``value``."""
    if math.isnan(value):
        return Stripped("NaN")
    if value == math.inf:
        return Stripped("Infinity")
    elif value == -math.inf:
        return Stripped("-Infinity")
    else:
        return Stripped(str(value))


# See: https://262.ecma-international.org/5.1/#sec-7.8.4
_BASE_ESCAPING_IN_TYPESCRIPT = {
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\v": "\\v",
    "\f": "\\f",
    "\r": "\\r",
}


def string_literal(
    text: str,
    without_enclosing: bool = False,
    in_backticks: bool = False,
) -> Stripped:
    """
    Generate a string literal from the ``text``.

    If ``without_enclosing`` is set, the enclosing quotes are omitted.

    If ``in_backticks`` is set, the enclosing quotes are assumed to be backticks
    and the escaping is performed according to:
    https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Template_literals
    """
    escaped_chars = []  # type: List[str]

    if len(text) > 0:
        iterator = iter(text)
        current_char = next(iterator, None)  # type: Optional[str]
        assert (
            current_char is not None
        ), "If `text` is non-empty, we have to observe at least a single character"

        while current_char is not None:
            next_char = next(iterator, None)

            escaped_char = _BASE_ESCAPING_IN_TYPESCRIPT.get(current_char, None)
            if escaped_char is not None:
                escaped_chars.append(escaped_char)
            else:
                if not in_backticks:
                    if current_char == '"':
                        escaped_chars.append('\\"')
                    else:
                        escaped_chars.append(current_char)
                else:
                    if current_char == "`":
                        escaped_chars.append("\\`")
                    elif (
                        current_char == "$"
                        and next_char is not None
                        and next_char == "{"
                    ):
                        escaped_chars.append("\\$")
                    else:
                        escaped_chars.append(current_char)

            current_char = next_char

    escaped = "".join(escaped_chars)

    if without_enclosing:
        return Stripped(escaped)
    else:
        if not in_backticks:
            return Stripped(f'"{escaped}"')
        else:
            return Stripped(f"`{escaped}`")


INDENT = "  "
INDENT2 = INDENT * 2


def bytes_literal(value: bytes) -> Tuple[Stripped, bool]:
    """
    Generate an expression representing the ``value``.

    If there are more than 8 bytes, a multi-line expression is returned.

    :param value: to be represented
    :return: (TypeScript expression, is multi-line)
    """
    if len(value) == 0:
        return Stripped("new Uint8Array()"), False

    writer = io.StringIO()

    if len(value) <= 8:
        items_joined = ", ".join(f"0x{byte:02x}" for byte in value)
        return Stripped(f"new Uint8Array([{items_joined}])"), False
    else:
        writer.write(
            f"""\
new Uint8Array(
{INDENT}["""
        )

        for start in range(0, len(value), 8):
            if start == 0:
                writer.write(f"\n{INDENT2}")
            else:
                writer.write(f",\n{INDENT2}")

            end = min(start + 8, len(value))

            assert start < end

            for i, byte in enumerate(value[start:end]):
                if i > 0:
                    writer.write(", ")

                writer.write(f"0x{byte:02x}")

        writer.write(f"\n{INDENT}]\n)")

        return Stripped(writer.getvalue()), True


def needs_escaping(text: str, in_backticks: bool = False) -> bool:
    """
    Check whether the ``text`` contains a character that needs escaping.

    If ``in_backticks`` is set, it checks that the ``text`` needs not be escaped if
    enclosed in backticks (instead of double quotes).
    """
    prev_character = None  # type: Optional[str]
    for character in text:
        if character in _BASE_ESCAPING_IN_TYPESCRIPT:
            return True

        if not in_backticks:
            if character == '"':
                return True
        else:
            if character == "`":
                return True

            if (
                prev_character is not None
                and prev_character == "$"
                and character == "{"
            ):
                return True

        prev_character = character

    return False


PRIMITIVE_TYPE_MAP = {
    intermediate.PrimitiveType.BOOL: Stripped("boolean"),
    intermediate.PrimitiveType.INT: Stripped("number"),
    intermediate.PrimitiveType.FLOAT: Stripped("number"),
    intermediate.PrimitiveType.STR: Stripped("string"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("Uint8Array"),
}


def _assert_all_primitive_types_are_mapped() -> None:
    """Assert that we have explicitly mapped all the primitive types to C#."""
    all_primitive_literals = set(literal.value for literal in PRIMITIVE_TYPE_MAP)

    mapped_primitive_literals = set(
        literal.value for literal in intermediate.PrimitiveType
    )

    all_diff = all_primitive_literals.difference(mapped_primitive_literals)
    mapped_diff = mapped_primitive_literals.difference(all_primitive_literals)

    messages = []  # type: List[str]
    if len(mapped_diff) > 0:
        messages.append(
            f"More primitive maps are mapped than there were defined "
            f"in the ``intermediate._types``: {sorted(mapped_diff)}"
        )

    if len(all_diff) > 0:
        messages.append(
            f"One or more primitive types in the ``intermediate._types`` were not "
            f"mapped in PRIMITIVE_TYPE_MAP: {sorted(all_diff)}"
        )

    if len(messages) > 0:
        raise AssertionError("\n\n".join(messages))


_assert_all_primitive_types_are_mapped()


def generate_type(
    type_annotation: intermediate.TypeAnnotationUnion,
    types_module: Optional[Stripped] = None,
) -> Stripped:
    """
    Generate the type for the given type annotation.

    If ``types_module`` is specified, it is used as prefix for the composite types.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        name: Identifier

        if isinstance(our_type, intermediate.Enumeration):
            name = typescript_naming.enum_name(type_annotation.our_type.name)

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return PRIMITIVE_TYPE_MAP[our_type.constrainee]

        elif isinstance(our_type, intermediate.ConcreteClass):
            name = typescript_naming.class_name(type_annotation.our_type.name)

        elif isinstance(our_type, intermediate.AbstractClass):
            name = typescript_naming.interface_name(type_annotation.our_type.name)

        else:
            assert_never(our_type)

        return Stripped(name if types_module is None else f"{types_module}.{name}")

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, types_module=types_module
        )

        return Stripped(f"Array<{item_type}>")

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        item_types = [
            generate_type(type_annotation=item, types_module=types_module)
            for item in type_annotation.items
        ]

        return Stripped(f"[{', '.join(item_types)}]")

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        value = generate_type(
            type_annotation=type_annotation.value, types_module=types_module
        )

        return Stripped(f"{value} | null")

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


INDENT3 = INDENT * 3
INDENT4 = INDENT * 4
INDENT5 = INDENT * 5
INDENT6 = INDENT * 6

WARNING = Stripped(
    """\
// This code has been automatically generated by aas-core-codegen.
// Do NOT edit or append."""
)


class GeneratorForLoopVariables:
    """
    Generate a unique variable name based on ``item`` stem.

    >>> generator = GeneratorForLoopVariables()

    >>> next(generator)
    'anItem'

    >>> next(generator)
    'anotherItem'

    >>> next(generator)
    'yetAnotherItem'

    >>> next(generator)
    'yetYetAnotherItem'
    """

    def __init__(self) -> None:
        """Initialize with the zero counter."""
        self.counter = 0

    def __next__(self) -> Identifier:
        """Generate the next variable name."""
        if self.counter == 0:
            result = Identifier("anItem")
        elif self.counter == 1:
            result = Identifier("anotherItem")
        elif self.counter == 2:
            result = Identifier("yetAnotherItem")
        else:
            result = Identifier("yet" + ("Yet" * (self.counter - 2)) + "AnotherItem")

        self.counter += 1

        return result


#: Name of the module where all the types are defined
TYPES_MODULE = Identifier("types")

#: Name of the module where all the constants are defined
CONSTANTS_MODULE = Identifier("constants")

#: Name of the module where all the verification logic resides
VERIFICATION_MODULE = Identifier("verification")


def environment_variable_prefix(package_identifier: Stripped) -> Stripped:
    """
    Generate the prefix for environment variables used in the package.

    >>> environment_variable_prefix(Stripped('@dummy-works/dummy'))
    'DUMMY'

    >>> environment_variable_prefix(Stripped('@aas-core-works/aas-core3.0-typescript'))
    'AAS_CORE3_0_TYPESCRIPT'
    """
    package_identifier_after_slash = (
        package_identifier.partition("/")[2] or package_identifier
    )

    return Stripped(
        re.sub("[^a-zA-Z_0-9]", "_", package_identifier_after_slash).upper()
    )
