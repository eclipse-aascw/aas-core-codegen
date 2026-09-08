"""Provide common functions shared among different Java code generation modules."""

from typing import List, cast, Optional, Sequence
import re

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, assert_never, indent_but_first_line
from aas_core_codegen.java import naming as java_naming


@ensure(lambda result: result.startswith('"'))
@ensure(lambda result: result.endswith('"'))
def string_literal(text: str) -> Stripped:
    """Generate a Java string literal from the ``text``."""
    escaped = []  # type: List[str]

    for character in text:
        if character == "\t":
            escaped.append("\\t")
        elif character == "\b":
            escaped.append("\\b")
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\f":
            escaped.append("\\f")
        elif character == "'":
            escaped.append("\\'")
        elif character == '"':
            escaped.append('\\"')
        elif character == "\\":
            escaped.append("\\\\")
        else:
            escaped.append(character)

    return Stripped('"{}"'.format("".join(escaped)))


def needs_escaping(text: str) -> bool:
    """Check whether the ``text`` contains a character that needs escaping."""
    for character in text:
        if character == "\t":
            return True
        elif character == "\b":
            return True
        elif character == "\n":
            return True
        elif character == "\r":
            return True
        elif character == "\f":
            return True
        elif character == "'":
            return True
        elif character == '"':
            return True
        elif character == "\\":
            return True
        else:
            pass

    return False


#: Maximal arity of a tuple for which we pre-generate a generic ``TupleN`` record
#: in :py:mod:`aas_core_codegen.java.lib._generate_common`.
#:
#: If you need larger tuples, please just bump this constant and re-generate.
MAX_TUPLE_ARITY = 8


PRIMITIVE_TYPE_MAP = {
    intermediate.PrimitiveType.BOOL: Stripped("Boolean"),
    intermediate.PrimitiveType.INT: Stripped("Long"),
    intermediate.PrimitiveType.FLOAT: Stripped("Double"),
    intermediate.PrimitiveType.STR: Stripped("String"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("byte[]"),
}


INDENT = "  "


# fmt: off
@require(
    lambda our_type_qualifier:
    not (our_type_qualifier is not None)
    or not our_type_qualifier.endswith('.')
)
# fmt: on
def generate_type(
    type_annotation: intermediate.TypeAnnotationUnion,
    our_type_qualifier: Optional[Stripped] = None,
) -> Stripped:
    """
    Generate the Java type for the given type annotation.

    ``our_type_prefix`` is appended to all our types, if specified.
    """
    our_type_prefix = "" if our_type_qualifier is None else f"{our_type_qualifier}."
    # BEFORE-RELEASE (empwilli, 2023-12-14): test in isolation
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(
                our_type_prefix + java_naming.enum_name(type_annotation.our_type.name)
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return PRIMITIVE_TYPE_MAP[our_type.constrainee]

        elif isinstance(our_type, intermediate.Class):
            # NOTE (empwilli, 2023-12-14):
            # We want to allow custom enhancements and wrappings around
            # our model classes. Therefore, we always operate over Java interfaces
            # instead of concrete classes, even if the class is a concrete one and
            # has no concrete descendants.

            return Stripped(our_type_prefix + java_naming.interface_name(our_type.name))

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, our_type_qualifier=our_type_qualifier
        )

        return Stripped(f"List<{item_type}>")

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # Tuples are represented as a static family of generic records,
        # ``Tuple1`` .. ``Tuple{MAX_TUPLE_ARITY}``, pre-generated in
        # :py:mod:`aas_core_codegen.java.lib._generate_common`. Unlike our types,
        # these records live in the ``common`` package regardless of the calling
        # context, so ``our_type_qualifier`` is *not* applied to the ``TupleN``
        # part itself -- only recursively to the item types.
        item_types = [
            generate_type(type_annotation=item, our_type_qualifier=our_type_qualifier)
            for item in type_annotation.items
        ]

        assert len(item_types) <= MAX_TUPLE_ARITY, (
            f"We only pre-generate Tuple1 .. Tuple{MAX_TUPLE_ARITY} "
            f"in the common package, but got a tuple of arity {len(item_types)}. "
            f"Please contact the developers if you need larger tuples."
        )

        tuple_type_name = f"Tuple{len(item_types)}"

        one_liner = f"{tuple_type_name}<{', '.join(item_types)}>"
        if len(one_liner) <= 60:
            return Stripped(one_liner)

        # NOTE (mristin):
        # The one-liner is too long to read comfortably (this happens in
        # practice for tuples mixing several class-typed items), so we break
        # after the opening ``<`` and put every item type on its own line.
        joined_item_types = ",\n".join(item_types)
        return Stripped(
            f"""\
{tuple_type_name}<
{INDENT}{indent_but_first_line(joined_item_types, INDENT)}>"""
        )

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        value = generate_type(
            type_annotation=type_annotation.value, our_type_qualifier=our_type_qualifier
        )
        return Stripped(f"Optional<{value}>")

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


@require(lambda item_exprs: len(item_exprs) > 0)
@require(lambda item_exprs: len(item_exprs) <= MAX_TUPLE_ARITY)
def generate_tuple_literal(item_exprs: Sequence[Stripped]) -> Stripped:
    """
    Generate a Java expression constructing a tuple record out of ``item_exprs``.

    We rely on the diamond operator for the type inference, so the type
    annotation of the tuple is not needed here.
    """
    tuple_type_name = f"Tuple{len(item_exprs)}"

    joined_item_exprs = ",\n".join(item_exprs)

    return Stripped(
        f"""\
new {tuple_type_name}<>(
{INDENT}{indent_but_first_line(joined_item_exprs, INDENT)})"""
    )


INDENT2 = INDENT * 2
INDENT3 = INDENT * 3
INDENT4 = INDENT * 4
INDENT5 = INDENT * 5
INDENT6 = INDENT * 6
INDENT7 = INDENT * 7
INDENT8 = INDENT * 8
INDENT9 = INDENT * 9
INDENT10 = INDENT * 10


INTERFACE_PKG = "model"
CLASS_PKG = "impl"
ENUM_PKG = "enums"


def interface_package_path(name: Stripped) -> Stripped:
    """Create the package path for an interface file."""
    return Stripped(f"{INTERFACE_PKG}/{name}.java")


def class_package_path(name: Stripped) -> Stripped:
    """Create the package path for an interface file."""
    return Stripped(f"{CLASS_PKG}/{name}.java")


def enum_package_path(name: Stripped) -> Stripped:
    """Create the package path for an interface file."""
    return Stripped(f"{ENUM_PKG}/{name}.java")


# noinspection RegExpSimplifiable
PACKAGE_IDENTIFIER_RE = re.compile(r"[a-z_0-9]*(\.[a-z][a-z_0-9]*)*")


class PackageIdentifier(str):
    """Capture a package identifier."""

    @require(lambda identifier: PACKAGE_IDENTIFIER_RE.fullmatch(identifier))
    def __new__(cls, identifier: str) -> "PackageIdentifier":
        return cast(PackageIdentifier, identifier)


WARNING = Stripped(
    """\
/*
 * This code has been automatically generated by aas-core-codegen.
 * Do NOT edit or append.
 */"""
)


class JavaFile:
    """Representation of a Java source file."""

    # fmt: off
    @require(lambda name, content: (len(name) > 0) and (len(content) > 0))
    @require(lambda content: content.endswith('\n'), "Trailing newline mandatory for valid end-of-files")
    # fmt: on
    def __init__(
        self,
        name: str,
        content: str,
    ):
        self.name = name
        self.content = content
