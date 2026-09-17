"""Provide common functions shared among different C# code generation modules."""
import re
from typing import Final, List, Mapping, Optional, Pattern, Sequence, cast

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped, assert_never, indent_but_first_line
from aas_core_codegen.csharp import naming as csharp_naming


@ensure(lambda result: result.startswith('"'))
@ensure(lambda result: result.endswith('"'))
def string_literal(text: str) -> Stripped:
    """Generate a C# string literal from the ``text``."""
    escaped = []  # type: List[str]

    for character in text:
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


PRIMITIVE_TYPE_MAP: Final[Mapping[intermediate.PrimitiveType, Stripped]] = {
    intermediate.PrimitiveType.BOOL: Stripped("bool"),
    intermediate.PrimitiveType.INT: Stripped("long"),
    intermediate.PrimitiveType.FLOAT: Stripped("double"),
    intermediate.PrimitiveType.STR: Stripped("string"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("byte[]"),
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
    Generate the C# type for the given type annotation.

    ``our_type_prefix`` is appended to all our types, if specified.
    """
    our_type_prefix = "" if our_type_qualifier is None else f"{our_type_qualifier}."
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return PRIMITIVE_TYPE_MAP[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return Stripped(
                our_type_prefix + csharp_naming.enum_name(type_annotation.our_type.name)
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            return PRIMITIVE_TYPE_MAP[our_type.constrainee]

        elif isinstance(our_type, intermediate.Class):
            # NOTE (mristin):
            # We want to allow custom enhancements and wrappings around
            # our model classes. Therefore, we always operate over C# interfaces
            # instead of concrete classes, even if the class is a concrete one and
            # has no concrete descendants.

            return Stripped(
                our_type_prefix + csharp_naming.interface_name(our_type.name)
            )

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is represented as a plain C# class, not an interface --
            # it is a closed set of alternatives, so there is no need to allow
            # custom enhancements or wrappings the way we do for the classes.
            return Stripped(our_type_prefix + csharp_naming.class_name(our_type.name))

        else:
            assert_never(our_type)

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, our_type_qualifier=our_type_qualifier
        )

        return Stripped(f"List<{item_type}>")

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        item_types = [
            generate_type(type_annotation=item, our_type_qualifier=our_type_qualifier)
            for item in type_annotation.items
        ]

        joined_item_types = ", ".join(item_types)

        if len(item_types) == 1:
            # NOTE (mristin):
            # A single-element value tuple has no literal syntax in C#, so we have
            # to spell out the generic type explicitly.
            return Stripped(f"System.ValueTuple<{joined_item_types}>")

        return Stripped(f"({joined_item_types})")

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        value = generate_type(
            type_annotation=type_annotation.value, our_type_qualifier=our_type_qualifier
        )
        return Stripped(f"{value}?")

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


INDENT: Final[str] = "    "
INDENT2: Final[str] = INDENT * 2
INDENT3: Final[str] = INDENT * 3
INDENT4: Final[str] = INDENT * 4
INDENT5: Final[str] = INDENT * 5
INDENT6: Final[str] = INDENT * 6
INDENT7: Final[str] = INDENT * 7
INDENT8: Final[str] = INDENT * 8


@require(lambda item_exprs: len(item_exprs) > 0)
def generate_tuple_literal(item_exprs: Sequence[Stripped]) -> Stripped:
    """Generate a value tuple literal out of the given item expressions."""
    joined_item_exprs = ",\n".join(item_exprs)

    if len(item_exprs) == 1:
        # NOTE (mristin):
        # A single-element value tuple has no literal syntax in C#, so we have
        # to resort to the explicit factory method.
        return Stripped(
            f"""\
System.ValueTuple.Create(
{INDENT}{indent_but_first_line(joined_item_exprs, INDENT)}
)"""
        )

    return Stripped(
        f"""\
(
{INDENT}{indent_but_first_line(joined_item_exprs, INDENT)}
)"""
    )


# noinspection RegExpSimplifiable
NAMESPACE_IDENTIFIER_RE: Final[Pattern[str]] = re.compile(
    r"[a-zA-Z_][a-zA-Z_0-9]*(\.[a-zA-Z_][a-zA-Z_0-9]*)*"
)


class NamespaceIdentifier(str):
    """Capture a namespace identifier."""

    @require(lambda identifier: NAMESPACE_IDENTIFIER_RE.fullmatch(identifier))
    def __new__(cls, identifier: str) -> "NamespaceIdentifier":
        return cast(NamespaceIdentifier, identifier)


WARNING: Final[Stripped] = Stripped(
    """\
/*
 * This code has been automatically generated by aas-core-codegen.
 * Do NOT edit or append.
 */"""
)


# fmt: off
@ensure(
    lambda namespace, result:
    not (namespace != "Aas") or len(result) == 1,
    "Exactly one block of stripped text to be appended to the list of using directives "
    "if this using directive is necessary"
)
@ensure(
    lambda namespace, result:
    not (namespace == "Aas") or len(result) == 0,
    "Empty list if no directive is necessary"
)
# fmt: on
def generate_using_aas_directive_if_necessary(
    namespace: NamespaceIdentifier,
) -> List[Stripped]:
    """Generate the using directive if the namespace does not equal ``Aas``."""
    if namespace == "Aas":
        return []

    if namespace.endswith(".Aas"):
        return [Stripped(f"using Aas = {namespace};")]

    return [Stripped(f"using Aas = {namespace};  // renamed")]


# NOTE (mristin):
# A C# primitive is not a valid part of an identifier as it is spelled
# (``byte[]``), so the primitives need monikers of their own. The monikers are
# *lower-case* on purpose: every one of our types is named through
# :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which always
# yields an upper-case initial, so a primitive moniker can never be confused
# for one of our types -- not even for an enumeration which somebody named
# ``String``. They are keyed by the meta-model primitive rather than by
# the C# spelling, so that the mapping is total by construction.
PRIMITIVE_TYPE_TO_MONIKER: Final[Mapping[intermediate.PrimitiveType, str]] = {
    intermediate.PrimitiveType.BOOL: "bool",
    intermediate.PrimitiveType.INT: "long",
    intermediate.PrimitiveType.FLOAT: "double",
    intermediate.PrimitiveType.STR: "string",
    intermediate.PrimitiveType.BYTEARRAY: "bytes",
}
assert all(
    primitive_type in PRIMITIVE_TYPE_TO_MONIKER
    for primitive_type in intermediate.PrimitiveType
)
assert all(
    moniker.islower() for moniker in PRIMITIVE_TYPE_TO_MONIKER.values()
), "The primitive monikers have to be lower-case, see the note above"


@ensure(lambda result: "_" not in result)
def leaf_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name a type which is neither a list nor a tuple.

    The result must not contain an underscore, since the underscore is what
    separates the tokens of a compound moniker. See :py:func:`type_moniker`.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return PRIMITIVE_TYPE_TO_MONIKER[primitive_type]

    # NOTE (mristin):
    # We name our types by ``generate_type`` so that the name of a reader can
    # not drift apart from the type of that very reader -- spelling the names
    # out here once caused exactly that.
    return generate_type(type_anno)


def type_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name the type in a way usable as a part of a C# identifier.

    The monikers are a Polish notation over ``_``-separated tokens: ``ListOf``
    takes exactly one argument, ``TupleOf{N}`` exactly ``N`` of them, and
    everything else is a leaf. A leaf token never contains an underscore
    (see :py:func:`leaf_moniker`), so the encoding is injective -- two
    different types can not be given the same moniker, and hence neither can
    two different de/serializers be given the same name, nor can two different
    types be conflated when the de/serializers are de-duplicated by
    their moniker.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "_".join(type_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{joined}"

    return leaf_moniker(type_anno)
