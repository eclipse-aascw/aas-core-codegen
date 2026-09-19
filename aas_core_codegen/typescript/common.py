"""Provide functions shared among different TypeScript code generation modules."""
import io
import math
import re
from typing import List, Tuple, Optional, Union

from icontract import require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, assert_never, Identifier
from aas_core_codegen.typescript import naming as typescript_naming


# region Type monikers


#: Moniker of a primitive type, see :py:func:`type_moniker`.
#:
#: The monikers are spelled in lower case, while a moniker of one of our types goes
#: through :py:func:`aas_core_codegen.naming.capitalized_camel_case`, so a primitive
#: can never be confused with a type which somebody named ``Str`` or ``Float``.
MONIKER_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: Identifier("bool"),
    intermediate.PrimitiveType.INT: Identifier("int"),
    intermediate.PrimitiveType.FLOAT: Identifier("float"),
    intermediate.PrimitiveType.STR: Identifier("str"),
    intermediate.PrimitiveType.BYTEARRAY: Identifier("bytes"),
}


def type_name_of_our_type(our_type: intermediate.OurType) -> Identifier:
    """Give out the name of the TypeScript type which stands for ``our_type``."""
    if isinstance(our_type, intermediate.Enumeration):
        return typescript_naming.enum_name(our_type.name)

    elif isinstance(our_type, intermediate.AbstractClass):
        return typescript_naming.interface_name(our_type.name)

    elif isinstance(our_type, intermediate.ConcreteClass):
        return typescript_naming.class_name(our_type.name)

    elif isinstance(our_type, intermediate.NamedUnion):
        return typescript_naming.union_name(our_type.name)

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        raise AssertionError("Expected to handle this case before")

    else:
        assert_never(our_type)

    raise AssertionError("Should not have gotten here")


def atomic_moniker(type_annotation: intermediate.TypeAnnotationUnion) -> Identifier:
    """
    Determine the leaf moniker of the atomic ``type_annotation``.

    The monikers are the parts out of which we build the names of the de/serializers
    which are keyed by a *structural* type -- a list, a tuple, an item at a fixed
    XML element name -- rather than by a symbol of the meta-model. A leaf moniker never
    contains an underscore: our types go through
    :py:func:`aas_core_codegen.naming.capitalized_camel_case`, and a primitive is
    spelled in lower case, which also keeps it apart from a type of the same name.
    See :py:func:`type_moniker` for the compound monikers built on top of these.
    """
    primitive_type = intermediate.try_primitive_type(type_annotation)
    if primitive_type is not None:
        return MONIKER_BY_PRIMITIVE_TYPE[primitive_type]

    # NOTE (mristin):
    # A JSON-able type is no type of the meta-model, so it needs a moniker of
    # its own, for the same reason as a primitive above. The initial is
    # *lower-case* so that it can never be confused for one of our types, which
    # all go through ``capitalized_camel_case``.
    if isinstance(type_annotation, intermediate.JsonValueTypeAnnotation):
        return Identifier("jsonValue")

    if isinstance(type_annotation, intermediate.JsonArrayTypeAnnotation):
        return Identifier("jsonArray")

    if isinstance(type_annotation, intermediate.JsonObjectTypeAnnotation):
        return Identifier("jsonObject")

    assert isinstance(
        type_annotation, intermediate.OurTypeAnnotation
    ), f"Expected an atomic type annotation, but got: {type_annotation}"

    return type_name_of_our_type(type_annotation.our_type)


def is_dispatched(type_anno: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether the run-time type of a value of ``type_anno`` is left open by
    the declared type.

    This is the case for an abstract class, for a concrete class with concrete
    descendants, and for a named union. Reading such a value, we have to decide what
    to construct before we have read anything, so something in the document has to
    tell us -- the local name of the XML element, or the ``modelType`` of the JSON
    object. Writing one, the instance itself answers, so the serialization simply
    dispatches on it.
    """
    if not isinstance(type_anno, intermediate.OurTypeAnnotation):
        return False

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.NamedUnion):
        return True

    if isinstance(our_type, intermediate.AbstractClass):
        return True

    if isinstance(our_type, intermediate.ConcreteClass):
        return len(our_type.concrete_descendants) > 0

    return False


def type_moniker(type_annotation: intermediate.TypeAnnotationUnion) -> str:
    """
    Determine the moniker of the ``type_annotation``.

    A moniker of a list or of a tuple is a Polish notation over ``_``-separated
    tokens: ``ListOf_{M}`` takes exactly one argument, and ``TupleOf{N}_{M}...``
    exactly ``N`` of them. As a leaf moniker never contains an underscore, such
    a name can always be split back into its parts, so the monikers are unique by
    construction and we need no check for collisions.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        monikers = "_".join(type_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{monikers}"

    return atomic_moniker(type_anno)


# endregion


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

        elif isinstance(our_type, intermediate.NamedUnion):
            name = typescript_naming.union_name(type_annotation.our_type.name)

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

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # The three JSON-able aliases are declared in the types module, next to
        # the classes whose properties are annotated with them.
        json_name: Identifier
        if isinstance(type_annotation, intermediate.JsonValueTypeAnnotation):
            json_name = Identifier("JsonValue")
        elif isinstance(type_annotation, intermediate.JsonArrayTypeAnnotation):
            json_name = Identifier("JsonArray")
        else:
            json_name = Identifier("JsonObject")

        return Stripped(
            json_name if types_module is None else f"{types_module}.{json_name}"
        )

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
