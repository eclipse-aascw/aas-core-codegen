"""
Generate Go identifiers based on the identifiers from the meta-model.

The methods all generate public names (capitalized), unless their prefix indicates
otherwise.
"""
from typing import List, Iterator, Optional, Final, FrozenSet

from icontract import require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier


@require(lambda identifier_part: len(identifier_part) > 0)
@require(lambda identifier_part: "_" not in identifier_part)
def _capitalize_or_leave_abbreviation(identifier_part: str) -> str:
    """
    Capitalize the first letter of ``text`` if it does not start with a capital letter.

    If the text already starts with a capital letter or a number, it is returned as-is.
    We thus assume that ``text`` is an abbreviation.

    >>> _capitalize_or_leave_abbreviation("something")
    'Something'

    >>> _capitalize_or_leave_abbreviation("SoMeThing")
    'SoMeThing'

    >>> _capitalize_or_leave_abbreviation("1something")
    '1something'

    >>> _capitalize_or_leave_abbreviation("URL")
    'URL'
    """
    if identifier_part[0].isupper():
        return identifier_part

    return identifier_part.capitalize()


def capital_camel_case(identifier: Identifier) -> Identifier:
    """
    Generate a capital Go camel-case name for something.

    This is usually used for public methods, members *etc.*

    >>> capital_camel_case(Identifier("something"))
    'Something'

    >>> capital_camel_case(Identifier("URL_to_something"))
    'URLToSomething'

    >>> capital_camel_case(Identifier("something_to_URL"))
    'SomethingToURL'
    """
    parts = identifier.split("_")

    return Identifier(
        "".join(
            _capitalize_or_leave_abbreviation(part) for part in parts if len(part) > 0
        )
    )


def _lower_camel_case(identifier: Identifier) -> Identifier:
    """
    Generate a lower-case Go camel-case name for something.

    This is usually used for private methods, members *etc.*

    >>> _lower_camel_case(Identifier("something"))
    'something'

    >>> _lower_camel_case(Identifier("Something"))
    'something'

    >>> _lower_camel_case(Identifier("URL_to_something"))
    'urlToSomething'

    >>> _lower_camel_case(Identifier("Something_to_URL"))
    'somethingToURL'
    """
    parts = identifier.split("_")

    cased = []  # type: List[str]
    parts_it = iter(parts)
    part = next(parts_it, None)
    assert part is not None, "Expected a non-empty identifier"

    cased.append(part.lower())

    part = next(parts_it, None)
    while part is not None:
        cased.append(_capitalize_or_leave_abbreviation(part))
        part = next(parts_it, None)

    return Identifier("".join(cased))


_KEYWORD_SET: Final[FrozenSet[Identifier]] = frozenset(
    [
        Identifier("break"),
        Identifier("case"),
        Identifier("chan"),
        Identifier("const"),
        Identifier("continue"),
        Identifier("default"),
        Identifier("defer"),
        Identifier("else"),
        Identifier("fallthrough"),
        Identifier("for"),
        Identifier("func"),
        Identifier("go"),
        Identifier("goto"),
        Identifier("if"),
        Identifier("import"),
        Identifier("interface"),
        Identifier("map"),
        Identifier("package"),
        Identifier("range"),
        Identifier("return"),
        Identifier("select"),
        Identifier("struct"),
        Identifier("switch"),
        Identifier("type"),
        Identifier("var"),
    ]
)

assert all(len(keyword) > 1 for keyword in _KEYWORD_SET), (
    f"We expect all the keywords to be at least 2 characters, "
    f"but we got at least one which is not: {_KEYWORD_SET=}."
    f"We built the naming logic based on this assumption since we uppercase the last"
    f"letter whenever the identifier conflicts with a keyword."
)

assert all(keyword.islower() for keyword in _KEYWORD_SET), (
    "We expected all the keywords to be lowercase, since that was the assumption "
    "when we renamed them to avoid conflicts, "
    f"but that is not the case: {_KEYWORD_SET=}"
)


@require(lambda keyword: keyword in _KEYWORD_SET)
def _transform_keyword_to_lowercase_with_upper_last_letter(
    keyword: Identifier,
) -> Identifier:
    """
    Transform the keyword identifier into a lowercase Go identifier.

    >>> _transform_keyword_to_lowercase_with_upper_last_letter(Identifier("interface"))
    'interfacE'
    """
    return Identifier(keyword[:-1] + keyword[-1].upper())


def interface_name(identifier: Identifier) -> Identifier:
    """Generate a Go public interface name based on its meta-model ``identifier``."""
    return Identifier(f"I{capital_camel_case(identifier)}")


def enum_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a public enum based on its meta-model ``identifier``.

    >>> enum_name(Identifier("something"))
    'Something'

    >>> enum_name(Identifier("URL_to_something"))
    'URLToSomething'
    """
    return capital_camel_case(identifier)


def enum_literal_name(
    enumeration_name: Identifier, literal_name: Identifier
) -> Identifier:
    """
    Generate a Go name for a public enum literal by prefixing it with the enumeration.

    >>> enum_literal_name(Identifier("URL"), Identifier("ID_short"))
    'URLIDShort'
    """
    return Identifier(
        capital_camel_case(enumeration_name) + capital_camel_case(literal_name)
    )


def private_struct_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a private struct based on its meta-model ``identifier``.

    >>> private_struct_name(Identifier("something"))
    'something'

    >>> private_struct_name(Identifier("URL_to_something"))
    'urlToSomething'

    >>> private_struct_name(Identifier("something_to_URL"))
    'somethingToURL'

    >>> private_struct_name(Identifier("interface"))
    'interfacE'

    >>> private_struct_name(Identifier("range"))
    'rangE'

    >>> private_struct_name(Identifier("type"))
    'typE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return _lower_camel_case(identifier)


def struct_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a public struct based on its meta-model ``identifier``.

    >>> struct_name(Identifier("something"))
    'Something'

    >>> struct_name(Identifier("URL_to_something"))
    'URLToSomething'
    """
    return capital_camel_case(identifier)


def union_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a named union based on its meta-model ``identifier``.

    A named union is represented as a plain Go struct, so the name follows
    the same convention as :py:func:`struct_name`, but is kept as a separate
    function since a named union is conceptually distinct from a class.

    >>> union_name(Identifier("something"))
    'Something'

    >>> union_name(Identifier("URL_to_something"))
    'URLToSomething'
    """
    return capital_camel_case(identifier)


def getter_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a public property getter based on its meta-model ``identifier``.

    >>> getter_name(Identifier("something"))
    'Something'

    >>> getter_name(Identifier("something_to_URL"))
    'SomethingToURL'
    """
    return capital_camel_case(identifier)


def setter_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a public property setter based on its meta-model ``identifier``.

    >>> setter_name(Identifier("something"))
    'SetSomething'

    >>> setter_name(Identifier("something_to_URL"))
    'SetSomethingToURL'
    """
    return capital_camel_case(Identifier("set_" + identifier))


def property_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a public property based on its meta-model ``identifier``.

    >>> property_name(Identifier("something"))
    'Something'

    >>> property_name(Identifier("something_to_URL"))
    'SomethingToURL'
    """
    return capital_camel_case(identifier)


def private_property_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a private property based on the ``identifier``.

    If the property conflicts with the Golang keyword ``type``, it is
    translated as ``typE``. This is ugly, but we couldn't find a better
    convention that hurts less.

    >>> private_property_name(Identifier("something"))
    'something'

    >>> private_property_name(Identifier("something_to_URL"))
    'somethingToURL'

    >>> private_property_name(Identifier("interface"))
    'interfacE'

    >>> private_property_name(Identifier("range"))
    'rangE'

    >>> private_property_name(Identifier("type"))
    'typE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return _lower_camel_case(identifier)


def private_method_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a private method based on the ``identifier``.

    >>> private_method_name(Identifier("something"))
    'something'

    >>> private_method_name(Identifier("something_to_URL"))
    'somethingToURL'

    >>> private_method_name(Identifier("interface"))
    'interfacE'

    >>> private_method_name(Identifier("range"))
    'rangE'

    >>> private_method_name(Identifier("type"))
    'typE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return _lower_camel_case(identifier)


def method_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a member method based on its meta-model ``identifier``.

    >>> method_name(Identifier("do_something"))
    'DoSomething'

    >>> method_name(Identifier("do_something_to_URL"))
    'DoSomethingToURL'
    """
    return capital_camel_case(identifier)


def function_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a function from its meta-model ``identifier``.

    >>> function_name(Identifier("do_something"))
    'DoSomething'

    >>> function_name(Identifier("do_something_to_URL"))
    'DoSomethingToURL'
    """
    return capital_camel_case(identifier)


def private_function_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a private function from its meta-model ``identifier``.

    >>> private_function_name(Identifier("do_something"))
    'doSomething'

    >>> private_function_name(Identifier("do_something_to_URL"))
    'doSomethingToURL'

    >>> private_function_name(Identifier("interface"))
    'interfacE'

    >>> private_function_name(Identifier("range"))
    'rangE'

    >>> private_function_name(Identifier("type"))
    'typE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return _lower_camel_case(identifier)


def argument_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for an argument based on its meta-model ``identifier``.

    If the argument conflicts with the Golang keyword ``type``, it is
    translated as ``aType``. This is ugly, but we couldn't find a better
    convention that hurts less.

    >>> argument_name(Identifier("something"))
    'something'

    >>> argument_name(Identifier("something_to_URL"))
    'somethingToURL'

    >>> argument_name(Identifier("interface"))
    'interfacE'

    >>> argument_name(Identifier("range"))
    'rangE'

    >>> argument_name(Identifier("type"))
    'typE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return _lower_camel_case(identifier)


def variable_name(identifier: Identifier) -> Identifier:
    """
    Generate a Go name for a variable based on its meta-model ``identifier``.

    If the variable conflicts with the Golang keyword ``type``, it is
    translated as ``typE``. This is ugly, but we couldn't find a better
    convention that hurts less.

    >>> variable_name(Identifier("something"))
    'something'

    >>> variable_name(Identifier("something_to_URL"))
    'somethingToURL'

    >>> variable_name(Identifier("interface"))
    'interfacE'

    >>> variable_name(Identifier("range"))
    'rangE'

    >>> variable_name(Identifier("type"))
    'typE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return _lower_camel_case(identifier)


def constant_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a public constant based on its meta-model ``identifier``.

    >>> constant_name(Identifier("something"))
    'Something'

    >>> constant_name(Identifier("URL_to_something"))
    'URLToSomething'
    """
    return capital_camel_case(identifier)


def private_constant_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a private constant based on its meta-model ``identifier``.

    >>> private_constant_name(Identifier("something"))
    'something'

    >>> private_constant_name(Identifier("URL_to_something"))
    'urlToSomething'

    >>> private_constant_name(Identifier("something_to_URL"))
    'somethingToURL'

    >>> private_constant_name(Identifier("interface"))
    'interfacE'

    >>> private_constant_name(Identifier("range"))
    'rangE'

    >>> private_constant_name(Identifier("type"))
    'typE'
    """
    # NOTE (mristin):
    # ``interface``, ``range`` and ``type'' are allowed in the specification, and
    # predate aas-core-codegen, so we have to handle them separately.
    if identifier == "interface":
        # noinspection SpellCheckingInspection
        return Identifier("interfacE")

    elif identifier == "range":
        # noinspection SpellCheckingInspection
        return Identifier("rangE")

    elif identifier == "type":
        return Identifier("typE")

    else:
        return _lower_camel_case(identifier)


def _over_potential_receivers(class_name: Identifier) -> Iterator[Identifier]:
    """Iterate over potential receiver names for the class."""
    yield Identifier("".join(part[0].lower() for part in class_name.split("_")))

    for i in range(2, 3):
        yield Identifier(class_name[0].lower() * i)


def receiver_name(
    cls: intermediate.ConcreteClass, prefix: Optional[str] = None
) -> Identifier:
    """
    Pick the name for the receiver variable in a method.

    Do not shadow a pre-defined set of variable names.

    If ``prefix`` is specified, append it to the receiver name.
    """
    total_arg_name_set = set(
        argument_name(arg.name) for method in cls.methods for arg in method.arguments
    )

    # NOTE (mristin, 2023-03-31):
    # The argument ``value`` is used in setters.
    total_arg_name_set.add(Identifier("value"))

    # NOTE (mristin, 2023-03-31):
    # The argument ``action`` is used in Descend and DescendOnce.
    total_arg_name_set.add(Identifier("action"))

    # NOTE (mristin, 2023-05-12):
    # The variable ``abort`` is used in Descend and DescendOnce.
    total_arg_name_set.add(Identifier("abort"))

    # NOTE (mristin, 2023-03-31):
    # The name ``enhancement`` is used as a property of an enhanced instance.
    # We skip it as a receiver to avoid confusion.
    total_arg_name_set.add(Identifier("enhancement"))

    # NOTE (mristin, 2023-03-31):
    # The name ``instance`` is used as a property of an enhanced instance.
    # We skip it as a receiver to avoid confusion.
    total_arg_name_set.add(Identifier("instance"))

    receiver = None  # type: Optional[Identifier]

    cls_name = cls.name if prefix is None else Identifier(prefix + cls.name)

    for potential_receiver in _over_potential_receivers(cls_name):
        if potential_receiver not in total_arg_name_set:
            receiver = potential_receiver
            break

    if receiver is None:
        raise AssertionError(
            f"(mristin, 2023-03-31): "
            f"No receiver name could be found for the class name {cls_name!r}. "
            f"Please contact the developers to extend the logic to add more potential "
            f"receiver names."
        )

    return receiver
