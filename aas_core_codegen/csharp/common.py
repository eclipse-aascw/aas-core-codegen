"""Provide common functions shared among different C# code generation modules."""
import re
from typing import Final, List, Mapping, Optional, Pattern, Sequence, cast

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Identifier,
    Stripped,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.csharp import naming as csharp_naming


@ensure(lambda result: result.startswith('"'))
@ensure(lambda result: result.endswith('"'))
def string_literal(text: str) -> Stripped:
    """Generate a C# string literal from the ``text``."""
    escaped: List[str] = []

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

    elif isinstance(type_annotation, intermediate.SetTypeAnnotation):
        item_type = generate_type(
            type_annotation=type_annotation.items, our_type_qualifier=our_type_qualifier
        )

        return Stripped(f"HashSet<{item_type}>")

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

    elif isinstance(type_annotation, intermediate.JsonValueTypeAnnotation):
        return Stripped("Nodes.JsonNode")

    elif isinstance(type_annotation, intermediate.JsonArrayTypeAnnotation):
        return Stripped("Nodes.JsonArray")

    elif isinstance(type_annotation, intermediate.JsonObjectTypeAnnotation):
        return Stripped("Nodes.JsonObject")

    else:
        assert_never(type_annotation)

    raise AssertionError("Should not have gotten here")


def is_value_type(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether ``type_annotation`` is represented as a C# value type.

    An optional of such a type is a ``System.Nullable``, so it is tested with
    ``HasValue`` and unwrapped with ``Value``, whereas an optional of
    a reference type is simply compared against ``null``.
    """
    primitive_type = intermediate.try_primitive_type(type_annotation)
    if primitive_type is not None:
        return primitive_type in (
            intermediate.PrimitiveType.BOOL,
            intermediate.PrimitiveType.INT,
            intermediate.PrimitiveType.FLOAT,
        )

    if isinstance(type_annotation, intermediate.OurTypeAnnotation) and isinstance(
        type_annotation.our_type, intermediate.Enumeration
    ):
        return True

    # NOTE (mristin):
    # A tuple is a ``System.ValueTuple``.
    return isinstance(type_annotation, intermediate.TupleTypeAnnotation)


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

    __slots__ = ()

    @require(lambda identifier: NAMESPACE_IDENTIFIER_RE.fullmatch(identifier))
    def __new__(cls, identifier: str) -> "NamespaceIdentifier":
        return cast(NamespaceIdentifier, identifier)


#: Name of the static class which holds the helpers shared by the transpiled code
#: in the types and in the verification
COMMON_CLASS: Final[Identifier] = Identifier("Common")


# NOTE (mristin):
# The names of the helpers generated per enumeration in ``SetHelpers`` start with
# a prefix, ``RankOf`` and ``CompareByRankOf``, with which no fixed helper there
# starts. Hence a generated name can never coincide with a fixed one, whatever
# the name of the enumeration, and there are no confusing overloads.


def rank_of_enumeration_name(enumeration: intermediate.Enumeration) -> Identifier:
    """Name the helper in ``SetHelpers`` which ranks the literals of ``enumeration``."""
    return Identifier(f"RankOf{csharp_naming.enum_name(enumeration.name)}")


def compare_by_rank_of_enumeration_name(
    enumeration: intermediate.Enumeration,
) -> Identifier:
    """Name the helper in ``SetHelpers`` which compares the literals by their rank."""
    return Identifier(f"CompareByRankOf{csharp_naming.enum_name(enumeration.name)}")


def set_items_comparison(items: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Generate the ``System.Comparison`` which sorts the ``items`` of a set.

    The sets are serialized sorted, in the same order in all the SDKs: ``false``
    before ``true``, the integers numerically, and the strings and the serialized
    values of the enumeration literals by their code points.
    """
    if isinstance(items, intermediate.OurTypeAnnotation) and isinstance(
        items.our_type, intermediate.Enumeration
    ):
        method_name = compare_by_rank_of_enumeration_name(items.our_type)
        return Stripped(f"{COMMON_CLASS}.SetHelpers.{method_name}")

    primitive_type = intermediate.try_primitive_type(items)
    assert primitive_type is not None, (
        f"Expected the items of a set to be primitives, constrained primitives "
        f"or enumeration literals, but got: {items}"
    )

    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped("System.Collections.Generic.Comparer<bool>.Default.Compare")

    elif primitive_type is intermediate.PrimitiveType.INT:
        return Stripped("System.Collections.Generic.Comparer<long>.Default.Compare")

    elif primitive_type is intermediate.PrimitiveType.STR:
        return Stripped(f"{COMMON_CLASS}.StringHelpers.CompareByCodePoints")

    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        raise AssertionError(
            f"Unexpected set of floats, as they are refused in "
            f"intermediate._translate._verify_items_of_sets: {items}"
        )

    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        raise AssertionError(
            f"Unexpected set of byte arrays, as they are refused in "
            f"intermediate._translate._verify_items_of_sets: {items}"
        )

    else:
        assert_never(primitive_type)


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
    namespace == "Our" or len(result) == 1,
    "Exactly one block of stripped text to be appended to the list of using directives "
    "if this using directive is necessary"
)
@ensure(
    lambda namespace, result:
    namespace != "Our" or len(result) == 0,
    "Empty list if no directive is necessary"
)
# fmt: on
def generate_using_our_directive_if_necessary(
    namespace: NamespaceIdentifier,
) -> List[Stripped]:
    """Generate the using directive if the namespace does not equal ``Our``."""
    if namespace == "Our":
        return []

    if namespace.endswith(".Our"):
        return [Stripped(f"using Our = {namespace};")]

    return [Stripped(f"using Our = {namespace};  // renamed")]


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
    # A JSON-able type is spelled as ``Nodes.JsonNode`` and friends, which is
    # no more a valid part of an identifier than ``byte[]`` is, so these need
    # monikers of their own as well. The initial is *lower-case* for exactly
    # the same reason as the primitives' above: an upper-case initial is what
    # every one of our own types starts with, so a lower-case one can never
    # be confused for, say, an enumeration which somebody named ``JsonValue``.
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return "jsonValue"

    if isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return "jsonArray"

    if isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return "jsonObject"

    # NOTE (mristin):
    # We name our types by ``generate_type`` so that the name of a reader can
    # not drift apart from the type of that very reader -- spelling the names
    # out here once caused exactly that.
    return generate_type(type_anno)


def type_moniker(type_anno: intermediate.TypeAnnotationUnion) -> str:
    """
    Name the type in a way usable as a part of a C# identifier.

    The monikers are a Polish notation over ``_``-separated tokens: ``ListOf``
    and ``SetOf`` take exactly one argument, ``TupleOf{N}`` exactly ``N`` of them, and
    everything else is a leaf. A leaf token never contains an underscore
    (see :py:func:`leaf_moniker`), so the encoding is injective -- two
    different types can not be given the same moniker, and hence neither can
    two different de/serializers be given the same name, nor can two different
    types be conflated when the de/serializers are de-duplicated by
    their moniker.
    """
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return f"ListOf_{type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.SetTypeAnnotation):
        return f"SetOf_{type_moniker(type_anno.items)}"

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        joined = "_".join(type_moniker(item) for item in type_anno.items)
        return f"TupleOf{len(type_anno.items)}_{joined}"

    return leaf_moniker(type_anno)
