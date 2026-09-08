"""Provide common functions shared among different Go code generation modules."""
import io
import math
import re
import urllib.parse
from typing import List, Sequence, Tuple, Optional

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    assert_never,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.golang import (
    naming as golang_naming,
    pointering as golang_pointering,
)


@ensure(lambda result: result.startswith('"'))
@ensure(lambda result: result.endswith('"'))
def string_literal(text: str) -> Stripped:
    """Generate a Go string literal from the ``text``."""
    escaped = []  # type: List[str]

    for character in text:
        code_point = ord(character)

        if character == "\a":
            escaped.append("\\a")
        elif character == "\b":
            escaped.append("\\b")
        elif character == "\f":
            escaped.append("\\f")
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\t":
            escaped.append("\\t")
        elif character == "\v":
            escaped.append("\\v")
        elif character == '"':
            escaped.append('\\"')
        elif character == "\\":
            escaped.append("\\\\")
        elif code_point < 32:
            # Non-printable ASCII characters
            escaped.append(f"\\x{ord(character):x}")
        elif 255 < code_point < 65536:
            # Above ASCII
            escaped.append(f"\\u{ord(character):04x}")
        elif code_point >= 65536:
            # Above Unicode Binary Multilingual Pane
            escaped.append(f"\\U{ord(character):08x}")
        else:
            escaped.append(character)

    return Stripped('"{}"'.format("".join(escaped)))


def needs_escaping(text: str) -> bool:
    """Check whether the ``text`` contains a character that needs escaping."""
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

    return False


def boolean_literal(value: bool) -> Stripped:
    """Generate the boolean literal corresponding to the ``value``."""
    return Stripped("true") if value else Stripped("false")


def float_literal(value: float) -> Stripped:
    """Generate the float literal.

    We assume that the precision of the literal is not critical and rely on
    Python's ``str(.)`` function. However, if you want to specify the exact
    number, you have to format the number yourself, probably using G17 representation.
    """
    if math.isnan(value):
        return Stripped("math.NaN")
    if value == math.inf:
        return Stripped("math.Inf(1)")
    elif value == -math.inf:
        return Stripped("math.Inf(-1)")
    else:
        return Stripped(str(value))


# NOTE (mristin, 2023-01-13):
# See: https://stackoverflow.com/questions/19094704/indentation-in-go-tabs-or-spaces
INDENT = "\t"


def bytes_literal(value: bytes) -> Tuple[Stripped, bool]:
    """
    Generate an expression representing the ``value``.

    If there are more than 8 bytes, a multi-line expression is returned.

    :param value: to be represented
    :return: (Golang expression, is multi-line)
    """
    if len(value) == 0:
        return Stripped("[...]byte{}"), False

    writer = io.StringIO()

    if len(value) <= 8:
        items_joined = ", ".join(f"0x{byte:02x}" for byte in value)
        return Stripped(f"[...]byte{{{items_joined}}}"), False
    else:
        writer.write(
            """\
[...]byte {"""
        )

        for start in range(0, len(value), 8):
            if start == 0:
                writer.write(f"\n{INDENT}")
            else:
                writer.write(f",\n{INDENT}")

            end = min(start + 8, len(value))

            assert start < end

            for i, byte in enumerate(value[start:end]):
                if i > 0:
                    writer.write(", ")

                writer.write(f"0x{byte:02x}")

        writer.write("\n}")

        return Stripped(writer.getvalue()), True


PRIMITIVE_TYPE_MAP = {
    intermediate.PrimitiveType.BOOL: Stripped("bool"),
    intermediate.PrimitiveType.INT: Stripped("int64"),
    intermediate.PrimitiveType.FLOAT: Stripped("float64"),
    intermediate.PrimitiveType.STR: Stripped("string"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("[]byte"),
}


def _assert_all_primitive_types_are_mapped() -> None:
    """Assert that we have explicitly mapped all the primitive types to Go."""
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

TYPES_PACKAGE = Identifier("aastypes")
CONSTANTS_PACKAGE = Identifier("aasconstants")
VERIFICATION_PACKAGE = Identifier("aasverification")
COMMON_PACKAGE = Identifier("aascommon")

#: Maximal arity of a tuple for which we pre-generate a generic ``TupleN`` struct
#: in :py:mod:`aas_core_codegen.golang.lib._generate_common`.
#:
#: If you need larger tuples, please just bump this constant and re-generate.
MAX_TUPLE_ARITY = 8


def generate_type(
    type_annotation: intermediate.TypeAnnotationUnion,
    types_package: Optional[Identifier] = None,
) -> Stripped:
    """
    Generate the Go type for the given type annotation.

    If ``types_package`` is specified, it is prepended to all our types.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enum_name = golang_naming.enum_name(type_annotation.our_type.name)
            if types_package is None:
                return enum_name

            return Stripped(f"{types_package}.{enum_name}")

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return PRIMITIVE_TYPE_MAP[our_type.constrainee]

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin, 2023-03-28):
            # We always refer to interfaces even in cases of concrete classes without
            # concrete descendants since we want to allow enhancing.
            interface_name = golang_naming.interface_name(our_type.name)

            if types_package is None:
                return interface_name

            return Stripped(f"{types_package}.{interface_name}")

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, types_package=types_package
        )

        return Stripped(f"[]{item_type}")

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        item_types = [
            generate_type(type_annotation=item, types_package=types_package)
            for item in type_annotation.items
        ]

        assert len(item_types) <= MAX_TUPLE_ARITY, (
            f"We only pre-generate Tuple1 .. Tuple{MAX_TUPLE_ARITY} "
            f"in {COMMON_PACKAGE}, but got a tuple of arity {len(item_types)}. "
            f"Please contact the developers if you need larger tuples."
        )

        joined_item_types = ", ".join(item_types)
        tuple_type_name = f"Tuple{len(item_types)}"

        return Stripped(f"{COMMON_PACKAGE}.{tuple_type_name}[{joined_item_types}]")

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        value_type = generate_type(
            type_annotation=type_annotation.value, types_package=types_package
        )

        if golang_pointering.is_pointer_type(type_annotation):
            return Stripped(f"*{value_type}")

        return value_type

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


@require(lambda item_exprs: len(item_exprs) > 0)
def generate_tuple_literal(
    type_annotation: intermediate.TupleTypeAnnotation,
    item_exprs: Sequence[Stripped],
    types_package: Optional[Identifier] = None,
) -> Stripped:
    """Generate a Go composite literal for a tuple of the given item expressions."""
    tuple_type = generate_type(
        type_annotation=type_annotation, types_package=types_package
    )

    joined_item_exprs = ",\n".join(item_exprs)

    return Stripped(
        f"""\
{tuple_type}{{
{INDENT}{indent_but_first_line(joined_item_exprs, INDENT)},
}}"""
    )


INDENT2 = INDENT * 2
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
    'v'

    >>> next(generator)
    'v1'

    >>> next(generator)
    'v2'
    """

    def __init__(self) -> None:
        """Initialize with the zero counter."""
        self.counter = 0

    def __next__(self) -> Identifier:
        """Generate the next variable name."""
        if self.counter == 0:
            result = Identifier("v")
        else:
            result = Identifier(f"v{self.counter}")

        self.counter += 1

        return result


def repo_url_to_environment_variable(repo_url: Stripped) -> Identifier:
    """
    Convert a repository URL to an environment-variable-style name.

    >>> repo_url_to_environment_variable(
    ...     Stripped('github.com/aas-core-works/aas-core3.0-golang')
    ... )
    'GITHUB_COM_AAS_CORE_WORKS_AAS_CORE3_0_GOLANG'

    >>> repo_url_to_environment_variable(
    ...     Stripped('github.com/org/repo/tree/main/sub/dir')
    ... )
    'GITHUB_COM_ORG_REPO_TREE_MAIN_SUB_DIR'

    >>> repo_url_to_environment_variable(
    ...     Stripped('gitlab.com/group/subgroup/repo')
    ... )
    'GITLAB_COM_GROUP_SUBGROUP_REPO'

    >>> repo_url_to_environment_variable(
    ...     Stripped('github.com/some owner/repo')
    ... )
    'GITHUB_COM_SOME_OWNER_REPO'

    >>> repo_url_to_environment_variable(
    ...     Stripped('https://github.com/owner/repo')
    ... )
    'GITHUB_COM_OWNER_REPO'

    >>> repo_url_to_environment_variable(Stripped(''))
    Traceback (most recent call last):
    ...
    ValueError: Repo URL must be a non-empty string.
    """
    if not isinstance(repo_url, str) or not repo_url.strip():
        raise ValueError("Repo URL must be a non-empty string.")

    # NOTE (mristin):
    # If scheme missing, we add one so urlsplit parses netloc correctly.
    parsed = urllib.parse.urlsplit(
        repo_url if "://" in repo_url else f"https://{repo_url}"
    )

    host = parsed.netloc or ""
    path = parsed.path or ""

    path = path.strip()
    path = path.strip("/")

    # Compose a canonical identifier string.
    canonical = host
    if len(path):
        canonical = f"{host}/{path}"

    # Convert to ENV_VAR format: uppercase, non-alnum -> underscore, collapse.
    env = re.sub(r"[^0-9A-Za-z]+", "_", canonical).upper()
    env = re.sub(r"_+", "_", env).strip("_")

    return Identifier(env)
