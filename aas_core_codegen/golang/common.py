"""Provide common functions shared among different Go code generation modules."""
import io
import math
import re
import urllib.parse
from typing import Final, List, Mapping, Sequence, Tuple, Optional

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
    escaped: List[str] = []

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


# NOTE (mristin):
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
    all_primitive_literals = {literal.value for literal in PRIMITIVE_TYPE_MAP}

    mapped_primitive_literals = {
        literal.value for literal in intermediate.PrimitiveType
    }

    all_diff = all_primitive_literals.difference(mapped_primitive_literals)
    mapped_diff = mapped_primitive_literals.difference(all_primitive_literals)

    messages: List[str] = []
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

TYPES_PACKAGE = Identifier("ourtypes")
CONSTANTS_PACKAGE = Identifier("ourconstants")
VERIFICATION_PACKAGE = Identifier("ourverification")
COMMON_PACKAGE = Identifier("ourcommon")

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
            # NOTE (mristin):
            # We always refer to interfaces even in cases of concrete classes without
            # concrete descendants since we want to allow enhancing.
            interface_name = golang_naming.interface_name(our_type.name)

            if types_package is None:
                return interface_name

            return Stripped(f"{types_package}.{interface_name}")

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is represented as a plain Golang struct, not an
            # interface -- unlike a class, the union struct itself is never
            # enhanced or wrapped, since it is merely a closed, tagged
            # container. Enhancement of the *instance held inside* the union
            # is unaffected by this: that instance is still typed as an
            # interface field within the union struct (see
            # ``_generate_named_union_struct`` in ``lib/_generate_types.py``),
            # so it is enhanced/wrapped like any other instance -- the
            # generated ``Wrap`` recurses into it via ``Underlying``/
            # ``FromUnderlying`` (see ``lib/_generate_enhancing.py``).
            union_name = golang_naming.union_name(our_type.name)

            if types_package is None:
                return Stripped(f"*{union_name}")

            return Stripped(f"*{types_package}.{union_name}")

        else:
            assert_never(our_type)

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, types_package=types_package
        )

        return Stripped(f"[]{item_type}")

    elif isinstance(type_annotation, intermediate.SetTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, types_package=types_package
        )

        return Stripped(f"map[{item_type}]struct{{}}")

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

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # The three JSON-able aliases are declared in the types package, next to
        # the structs whose fields are annotated with them. All three are
        # nilable, so an optional one needs no pointer -- see
        # :py:func:`aas_core_codegen.golang.pointering.is_pointer_type`.
        json_name: Identifier
        if isinstance(type_annotation, intermediate.JsonValueTypeAnnotation):
            json_name = Identifier("JsonValue")
        elif isinstance(type_annotation, intermediate.JsonArrayTypeAnnotation):
            json_name = Identifier("JsonArray")
        else:
            json_name = Identifier("JsonObject")

        if types_package is None:
            return Stripped(json_name)

        return Stripped(f"{types_package}.{json_name}")

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


# NOTE (mristin):
# A Golang primitive is not usable as a part of an identifier as it is spelled
# (``[]byte``), so the primitives need monikers of their own. The monikers are
# *lower-case* on purpose: every one of our types is named through
# :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which always yields
# an upper-case initial, so a primitive moniker can never be confused for one of
# our types -- not even for an enumeration which somebody named ``String``. They
# are keyed by the meta-model primitive rather than by the Golang spelling, so that
# the mapping is total by construction.
_PRIMITIVE_TYPE_TO_MONIKER: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "bool",
    intermediate.PrimitiveType.INT: "long",
    intermediate.PrimitiveType.FLOAT: "double",
    intermediate.PrimitiveType.STR: "string",
    intermediate.PrimitiveType.BYTEARRAY: "bytes",
}
assert all(
    literal in _PRIMITIVE_TYPE_TO_MONIKER for literal in intermediate.PrimitiveType
)
assert all(
    moniker.islower() for moniker in _PRIMITIVE_TYPE_TO_MONIKER.values()
), "The primitive monikers have to be lower-case, see the note above"


@ensure(lambda result: "_" not in result)
def leaf_moniker(type_anno: intermediate.AtomicTypeAnnotation) -> str:
    """
    Name the type of ``type_anno`` as a part of an identifier.

    Everything which is not a primitive is named as the Golang type is, so that
    the name of a function can not drift apart from the type it operates on.

    The result must not contain an underscore, since the underscore is what
    separates the tokens of a compound moniker, see :py:func:`type_moniker`.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_MONIKER[primitive_type]

    # NOTE (mristin):
    # A JSON-able type is no type of the meta-model, so it needs a moniker of
    # its own, for the same reason as a primitive above. The initial is
    # *lower-case* so that it can never be confused for one of our types, which
    # all go through ``capitalized_camel_case``.
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return "jsonValue"

    if isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return "jsonArray"

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return "jsonObject"

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Unexpected type annotation for a moniker: {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return golang_naming.enum_name(our_type.name)

    if isinstance(our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)):
        return golang_naming.interface_name(our_type.name)

    assert isinstance(
        our_type, intermediate.NamedUnion
    ), f"Unexpected our type for a moniker: {our_type}"

    return golang_naming.union_name(our_type.name)


def type_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name the type in a way usable as a part of a Golang identifier.

    The monikers are a Polish notation over ``_``-separated tokens: ``ListOf``
    and ``SetOf`` take exactly one argument, ``TupleOf{N}`` exactly ``N`` of them, and
    everything else is a leaf. A leaf token never contains an underscore
    (see :py:func:`leaf_moniker`), so the encoding is injective -- two
    different types can not be given the same moniker, and hence neither can
    two different functions be given the same name.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"SetOf_{type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "_".join(type_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{joined}"

    assert isinstance(
        type_anno, intermediate.AtomicTypeAnnotationAsTuple
    ), f"Unexpected type annotation for a moniker: {type_anno}"

    return leaf_moniker(type_anno)


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
INDENT7 = INDENT * 7
INDENT8 = INDENT * 8

#: Maximum number of columns of a line of the generated code, with a tab counted as
#: :py:data:`TAB_WIDTH` columns
MAX_LINE_LENGTH = 88

#: Number of columns a tab of indention takes up in the generated code
TAB_WIDTH = 4


def join_arguments(arguments: Sequence[str], indention: int) -> str:
    """
    Join the ``arguments`` of a call, on a single line if they fit on one.

    The arguments are expected to be written on their own line(s), indented by
    ``indention`` tabs, and followed by the closing parenthesis on yet another line.
    A trailing comma is appended, as Golang requires it there.
    """
    joined = ", ".join(arguments) + ","

    if "\n" not in joined and indention * TAB_WIDTH + len(joined) <= MAX_LINE_LENGTH:
        return joined

    return ",\n".join(arguments) + ","


WARNING = Stripped(
    """\
// This code has been automatically generated by aas-core-codegen.
// Do NOT edit or append."""
)


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


def names_package(blocks: Sequence[str], qualifier: str) -> bool:
    """
    Check whether any of the ``blocks`` names the package behind ``qualifier``.

    This decides whether that package is imported at all: an unused import does
    not compile in Go, and what a generated file names depends on the meta-model.

    Mind that the qualifier has to stand on its own. ``ourtesting.RecordMode``
    names neither ``testing`` nor ``our``.
    """
    pattern = re.compile(r"(?<![\w.])" + re.escape(qualifier) + r"\.")
    return any(pattern.search(block) is not None for block in blocks)


def sorted_set_items_expr(
    set_expr: str, items: intermediate.TypeAnnotationUnion, column: int
) -> Stripped:
    """
    Generate the expression giving the items of ``set_expr`` as a sorted slice.

    The expression is expected to start at the ``column`` of its line, counting
    a tab as :py:data:`TAB_WIDTH` characters. If it does not fit on that line,
    we split it over multiple lines.

    We sort the items in the order of their serialization, which is the same in
    all the targets: ``false`` before ``true``, the integers numerically, and
    the strings and the literals of the enumerations by the code points of their
    text. Go compares the strings byte by byte, and the order of the bytes in
    UTF-8 is the order of the code points.

    A nil set gives a nil slice, so that an absent optional set stays absent.
    """
    less: str

    primitive_type = intermediate.try_primitive_type(items)
    if primitive_type is intermediate.PrimitiveType.BOOL:
        less = "ourcommon.LessBool"

    elif primitive_type is intermediate.PrimitiveType.INT:
        less = "ourcommon.LessOrdered[int64]"

    elif primitive_type is intermediate.PrimitiveType.STR:
        less = "ourcommon.LessOrdered[string]"

    elif primitive_type is not None:
        raise AssertionError(
            f"Unexpected items of a set, as we refuse the sets of {primitive_type} "
            f"in intermediate._translate._verify_items_of_sets: {items}"
        )

    elif isinstance(items, intermediate.OurTypeAnnotation) and isinstance(
        items.our_type, intermediate.Enumeration
    ):
        less = "ourstringification." + golang_naming.function_name(
            Identifier(f"less_by_rank_of_{items.our_type.name}")
        )

    else:
        raise AssertionError(
            f"Unexpected items of a set, as we refuse them "
            f"in intermediate._translate._verify_items_of_sets: {items}"
        )

    single_line = f"ourcommon.SortedKeys({set_expr}, {less})"
    if column + len(single_line) <= MAX_LINE_LENGTH:
        return Stripped(single_line)

    return Stripped(
        f"""\
ourcommon.SortedKeys(
{INDENT}{set_expr},
{INDENT}{less},
)"""
    )
