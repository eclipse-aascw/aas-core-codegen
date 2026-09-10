"""Provide common functions shared among different Python code generation modules."""
import enum
import io
import re
from typing import List, cast, Tuple, Optional, Mapping

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    assert_never,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.python import naming as python_naming


class StringQuoting(enum.Enum):
    """Represent how strings should be quoted as Python literals."""

    SINGLE_QUOTES = 0
    DOUBLE_QUOTES = 1


# region Different string escapings

# See: https://python-reference.readthedocs.io/en/latest/docs/str/escapes.html
_BASE_ESCAPING_IN_PYTHON = {
    "\\": "\\\\",
    "\a": "\\a",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\v": "\\v",
}

_ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES = {
    **_BASE_ESCAPING_IN_PYTHON,
    **{'"': '\\"'},
}

_ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES_AND_DUPLICATE_CURLY_BRACKETS = {
    **_ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES,
    **{
        "{": "{{",
        "}": "}}",
    },
}

_ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES = {
    **_BASE_ESCAPING_IN_PYTHON,
    **{"'": "\\'"},
}

_ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES_AND_DUPLICATE_CURLY_BRACKETS = {
    **_ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES,
    **{
        "{": "{{",
        "}": "}}",
    },
}

# endregion


# fmt: off
@ensure(
    lambda quoting, without_enclosing, result:
    not (quoting is StringQuoting.SINGLE_QUOTES and not without_enclosing)
    or (
        result.startswith("'") and result.endswith("'")
    )
)
@ensure(
    lambda quoting, without_enclosing, result:
    not (quoting is StringQuoting.DOUBLE_QUOTES and not without_enclosing)
    or (
        result.startswith('"') and result.endswith('"')
    )
)
# fmt: on
def string_literal(
    text: str,
    quoting: Optional[StringQuoting] = None,
    without_enclosing: bool = False,
    duplicate_curly_brackets: bool = False,
) -> Stripped:
    """
    Generate a string literal from the ``text``.

    If ``quoting`` is not set, check which quotes occur more often (single-quotes or
    double-quotes), and enclose the literal such that we need to escape as little as
    possible.

    If ``without_enclosing`` is set, the enclosing characters (double-quotes or
    single-quotes) are omitted.

    If ``duplicate_curly_brackets`` is set, all the opening and closing curly brackets
    (``{`` and ``}``) are duplicated (``{{`` and ``}}``, respectively).
    """
    mapping: Mapping[str, str]
    enclosing: str

    if quoting is None:
        if text.count("'") <= text.count('"'):
            mapping = _ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES
            enclosing = "'"

        else:
            mapping = _ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES
            enclosing = '"'

    elif quoting is StringQuoting.SINGLE_QUOTES:
        mapping = _ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES
        enclosing = "'"

    elif quoting is StringQuoting.DOUBLE_QUOTES:
        mapping = _ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES
        enclosing = '"'
    else:
        assert_never(quoting)

    if duplicate_curly_brackets:
        if mapping is _ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES:
            mapping = (
                _ESCAPING_IN_PYTHON_INCLUDING_DOUBLE_QUOTES_AND_DUPLICATE_CURLY_BRACKETS
            )
        elif mapping is _ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES:
            mapping = (
                _ESCAPING_IN_PYTHON_INCLUDING_SINGLE_QUOTES_AND_DUPLICATE_CURLY_BRACKETS
            )
        else:
            raise AssertionError(f"Unexpected mapping: {mapping}")

    escaped = "".join(mapping.get(character, character) for character in text)

    if without_enclosing:
        return Stripped(escaped)
    else:
        return Stripped(f"{enclosing}{escaped}{enclosing}")


# fmt: off
@ensure(
    lambda result:
    not result[1] or all(
        line.startswith('b"') and line.endswith('"')
        for line in result[0].splitlines()
    ),
    "If multi-line, the text is lines of bytes literals"
)
@ensure(
    lambda result:
    not (not result[1])
    or (
        '\n' not in result[0]
        and result[0].startswith('b"') and result[0].endswith('"')
    )
)
# fmt: on
def bytes_literal(value: bytes) -> Tuple[Stripped, bool]:
    """
    Generate a literal representing the ``value``.

    If there are more than 8 bytes, a multi-line literal is returned.

    :param value: to be represented
    :return: (Python literal, is multi-line)
    """
    writer = io.StringIO()

    multi_line: bool

    if len(value) <= 8:
        writer.write('b"')
        for byte in value:
            writer.write(f"\\x{byte:02x}")

        writer.write('"')

        multi_line = False
    else:
        for i in range(0, len(value), 8):
            if i > 0:
                writer.write("\n")

            start = i
            end = min(i + 8, len(value))

            assert start < end

            writer.write('b"')
            for byte in value[start:end]:
                writer.write(f"\\x{byte:02x}")
            writer.write('"')

        multi_line = True

    return Stripped(writer.getvalue()), multi_line


def needs_escaping(text: str, also_check_curly_brackets: bool = False) -> bool:
    """
    Check whether the ``text`` contains a character that needs escaping.

    If ``also_check_curly_brackets`` is set, it also checks that the ``text``
    does not contain any curly brackets, which would need to be properly escaped
    in string interpolations.
    """
    for character in text:
        if character == "\a":
            return True
        elif character == "\b":
            return True
        elif character == "\f":
            return True
        elif character == "\n":
            return True
        elif character == "\r":
            return True
        elif character == "\t":
            return True
        elif character == "\v":
            return True
        elif character == '"':
            return True
        elif character == "\\":
            return True
        else:
            pass

    if also_check_curly_brackets:
        if "{" in text:
            return True

        if "}" in text:
            return True

    return False


PRIMITIVE_TYPE_MAP = {
    intermediate.PrimitiveType.BOOL: Stripped("bool"),
    intermediate.PrimitiveType.INT: Stripped("int"),
    intermediate.PrimitiveType.FLOAT: Stripped("float"),
    intermediate.PrimitiveType.STR: Stripped("str"),
    # NOTE (mristin, 2022-10-14):
    # Since most Python functions and encodings deal with ``bytes`` instead of
    # ``bytearrays``, we decided to use ``bytes`` in the SDK.
    intermediate.PrimitiveType.BYTEARRAY: Stripped("bytes"),
}


def _assert_all_primitive_types_are_mapped() -> None:
    """Assert that all the primitive types are mapped to Python ones."""
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


INDENT = "    "


def generate_type(
    type_annotation: intermediate.TypeAnnotationUnion,
    types_module: Optional[Identifier] = None,
) -> Stripped:
    """
    Generate the type for the given type annotation.

    If ``types_module`` is specified, it is used as prefix for the composite types.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        # NOTE (mristin, 2022-09-17):
        # If no ``types_module``, we mark all enumerations and classes as string
        # literals to avoid problems caused by lack of forward declaration in Python. If
        # we created a dependency graph, we could strip away some quotes, but we believe
        # that consistency is better for readability than no quotes in some cases.

        if isinstance(our_type, intermediate.Enumeration):
            if types_module is None:
                return Stripped(
                    repr(python_naming.enum_name(type_annotation.our_type.name))
                )
            else:
                return Stripped(
                    f"{types_module}"
                    f".{python_naming.enum_name(type_annotation.our_type.name)}"
                )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return PRIMITIVE_TYPE_MAP[our_type.constrainee]

        elif isinstance(our_type, intermediate.Class):
            if types_module is None:
                return Stripped(repr(python_naming.class_name(our_type.name)))
            else:
                return Stripped(
                    f"{types_module}.{python_naming.class_name(our_type.name)}"
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            if types_module is None:
                return Stripped(repr(python_naming.union_name(our_type.name)))
            else:
                return Stripped(
                    f"{types_module}.{python_naming.union_name(our_type.name)}"
                )

        else:
            assert_never(our_type)

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, types_module=types_module
        )

        return Stripped(f"List[{item_type}]")

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        item_types = [
            generate_type(type_annotation=item, types_module=types_module)
            for item in type_annotation.items
        ]

        # NOTE (mristin):
        # We first determine the length of the one-liner *without* actually
        # joining ``item_types`` into it, so that we do not throw away that
        # join in the (in practice common, for tuples mixing several
        # class-typed items) case where it turns out to be too long to read
        # comfortably and we have to re-join with a different separator
        # anyhow. ``len("Tuple[]") == 7`` and every separator between two
        # items is ``", "`` (2 characters).
        one_liner_length = (
            7
            + sum(len(item_type) for item_type in item_types)
            + 2 * (len(item_types) - 1)
        )

        if one_liner_length <= 60:
            return Stripped(f"Tuple[{', '.join(item_types)}]")

        # NOTE (mristin):
        # Break each item type onto its own line.
        joined_item_types = ",\n".join(item_types)
        return Stripped(
            f"""\
Tuple[
{INDENT}{indent_but_first_line(joined_item_types, INDENT)},
]"""
        )

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        value = generate_type(
            type_annotation=type_annotation.value, types_module=types_module
        )

        if "\n" not in value:
            return Stripped(f"Optional[{value}]")

        # NOTE (mristin):
        # ``value`` is already broken over multiple lines (see, *e.g.*, the
        # ``TupleTypeAnnotation`` case above), so we follow the same
        # bracket-per-line style here instead of squeezing it onto one line.
        return Stripped(
            f"""\
Optional[
{INDENT}{indent_but_first_line(value, INDENT)}
]"""
        )

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


INDENT2 = INDENT * 2
INDENT3 = INDENT * 3
INDENT4 = INDENT * 4
INDENT5 = INDENT * 5
INDENT6 = INDENT * 6

WARNING = Stripped(
    """\
# This code has been automatically generated by aas-core-codegen.
# Do NOT edit or append."""
)

QUALIFIED_MODULE_NAME_RE = re.compile(
    r"[a-zA-Z_][a-zA-Z_0-9]*(\.[a-zA-Z_][a-zA-Z_0-9]*)*"
)


class QualifiedModuleName(str):
    """Capture a qualified name of a module."""

    @require(lambda identifier: QUALIFIED_MODULE_NAME_RE.fullmatch(identifier))
    def __new__(cls, identifier: str) -> "QualifiedModuleName":
        return cast(QualifiedModuleName, identifier)


class GeneratorForLoopVariables:
    """
    Generate a unique variable name based on ``item`` stem.

    >>> generator = GeneratorForLoopVariables()

    >>> next(generator)
    'an_item'

    >>> next(generator)
    'another_item'

    >>> next(generator)
    'yet_another_item'

    >>> next(generator)
    'yet_yet_another_item'
    """

    def __init__(self) -> None:
        """Initialize with the zero counter."""
        self.counter = 0

    def __next__(self) -> Identifier:
        """Generate the next variable name."""
        if self.counter == 0:
            result = Identifier("an_item")
        elif self.counter == 1:
            result = Identifier("another_item")
        else:
            result = Identifier(("yet_" * (self.counter - 1)) + "another_item")

        self.counter += 1

        return result
