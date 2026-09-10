"""
Generate C++ identifiers based on the identifiers from the meta-model.

The methods all generate public names, unless their prefix indicates
otherwise.

We follow the Google C++ code style,
see: https://google.github.io/styleguide/cppguide.html#Naming
"""
from typing import Final, FrozenSet

from icontract import require

from aas_core_codegen import naming
from aas_core_codegen.common import Identifier


def interface_name(identifier: Identifier) -> Identifier:
    """Generate a C++ interface name based on its meta-model ``identifier``."""
    return Identifier(f"I{naming.capitalized_camel_case(identifier)}")


def enum_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for an enum based on its meta-model ``identifier``.

    >>> enum_name(Identifier("something"))
    'Something'

    >>> enum_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return naming.capitalized_camel_case(identifier)


def enum_literal_name(literal_name: Identifier) -> Identifier:
    """
    Generate a C++ name for an enum literal.

    >>> enum_literal_name(Identifier("ID_short"))
    'kIdShort'
    """
    return Identifier(f"k{naming.capitalized_camel_case(literal_name)}")


def class_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a class based on its meta-model ``identifier``.

    >>> class_name(Identifier("something"))
    'Something'

    >>> class_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return naming.capitalized_camel_case(identifier)


def union_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a named union based on its meta-model ``identifier``.

    The name is used for a ``using`` alias to a ``std::variant``, so it follows
    the same convention as :py:func:`class_name`/:py:func:`enum_name`, without
    the ``I``-prefix used by :py:func:`interface_name` -- a named union is
    not an interface.

    >>> union_name(Identifier("something"))
    'Something'

    >>> union_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return naming.capitalized_camel_case(identifier)


_KEYWORD_SET: Final[FrozenSet[Identifier]] = frozenset(
    {
        Identifier("alignas"),
        Identifier("alignof"),
        Identifier("and"),
        Identifier("and_eq"),
        Identifier("asm"),
        Identifier("auto"),
        Identifier("bitand"),
        Identifier("bitor"),
        Identifier("bool"),
        Identifier("break"),
        Identifier("case"),
        Identifier("catch"),
        Identifier("char"),
        Identifier("char8_t"),
        Identifier("char16_t"),
        Identifier("char32_t"),
        Identifier("class"),
        Identifier("compl"),
        Identifier("concept"),
        Identifier("const"),
        Identifier("consteval"),
        Identifier("constexpr"),
        Identifier("constinit"),
        Identifier("const_cast"),
        Identifier("continue"),
        Identifier("contract_assert"),
        Identifier("co_await"),
        Identifier("co_return"),
        Identifier("co_yield"),
        Identifier("decltype"),
        Identifier("default"),
        Identifier("delete"),
        Identifier("do"),
        Identifier("double"),
        Identifier("dynamic_cast"),
        Identifier("else"),
        Identifier("enum"),
        Identifier("explicit"),
        Identifier("export"),
        Identifier("extern"),
        Identifier("false"),
        Identifier("float"),
        Identifier("for"),
        Identifier("friend"),
        Identifier("goto"),
        Identifier("if"),
        Identifier("inline"),
        Identifier("int"),
        Identifier("long"),
        Identifier("mutable"),
        Identifier("namespace"),
        Identifier("new"),
        Identifier("noexcept"),
        Identifier("not"),
        Identifier("not_eq"),
        Identifier("nullptr"),
        Identifier("operator"),
        Identifier("or"),
        Identifier("or_eq"),
        Identifier("private"),
        Identifier("protected"),
        Identifier("public"),
        Identifier("register"),
        Identifier("reinterpret_cast"),
        Identifier("requires"),
        Identifier("return"),
        Identifier("short"),
        Identifier("signed"),
        Identifier("sizeof"),
        Identifier("static"),
        Identifier("static_assert"),
        Identifier("static_cast"),
        Identifier("struct"),
        Identifier("switch"),
        Identifier("template"),
        Identifier("this"),
        Identifier("thread_local"),
        Identifier("throw"),
        Identifier("true"),
        Identifier("try"),
        Identifier("typedef"),
        Identifier("typeid"),
        Identifier("typename"),
        Identifier("union"),
        Identifier("unsigned"),
        Identifier("using"),
        Identifier("virtual"),
        Identifier("void"),
        Identifier("volatile"),
        Identifier("wchar_t"),
        Identifier("while"),
        Identifier("xor"),
        Identifier("xor_eq"),
    }
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

assert all(not keyword.startswith("mutable_") for keyword in _KEYWORD_SET), (
    "We expected all the keywords to not start with ``mutable_``, since that was "
    "the assumption when we renamed them to avoid conflicts, "
    f"but that is not the case: {_KEYWORD_SET=}"
)

assert all(not keyword.startswith("set_") for keyword in _KEYWORD_SET), (
    "We expected all the keywords to not start with ``set_``, since that was "
    "the assumption when we renamed them to avoid conflicts, "
    f"but that is not the case: {_KEYWORD_SET=}"
)

assert all(not keyword.endswith("_") for keyword in _KEYWORD_SET), (
    "We expected all the keywords to not end with ``_``, since that was "
    "the assumption when we renamed them to avoid conflicts, "
    f"but that is not the case: {_KEYWORD_SET=}"
)


@require(lambda keyword: keyword in _KEYWORD_SET)
def _transform_keyword_to_lowercase_with_upper_last_letter(
    keyword: Identifier,
) -> Identifier:
    """
    Transform the keyword identifier into a lowercase Go identifier.

    >>> _transform_keyword_to_lowercase_with_upper_last_letter(Identifier("void"))
    'voiD'
    """
    return Identifier(keyword[:-1] + keyword[-1].upper())


def getter_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a property getter based on its meta-model ``identifier``.

    >>> getter_name(Identifier("something"))
    'something'

    >>> getter_name(Identifier("something_to_URL"))
    'something_to_url'

    >>> getter_name(Identifier("void"))
    'voiD'

    >>> getter_name(Identifier("static_cast"))
    'static_casT'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return naming.lower_snake_case(identifier)


def mutable_getter_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a property getter based on its meta-model ``identifier``.

    >>> mutable_getter_name(Identifier("something"))
    'mutable_something'

    >>> mutable_getter_name(Identifier("something_to_URL"))
    'mutable_something_to_url'
    """
    return naming.lower_snake_case(Identifier(f"mutable_{identifier}"))


def setter_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a property setter based on its meta-model ``identifier``.

    >>> setter_name(Identifier("something"))
    'set_something'

    >>> setter_name(Identifier("something_to_URL"))
    'set_something_to_url'
    """
    return naming.lower_snake_case(Identifier(f"set_{identifier}"))


def private_property_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a private property based on the ``identifier``.

    >>> private_property_name(Identifier("something"))
    'something_'

    >>> private_property_name(Identifier("something_to_URL"))
    'something_to_url_'
    """
    return Identifier(f"{naming.lower_snake_case(identifier)}_")


def method_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a member method based on its meta-model ``identifier``.

    >>> method_name(Identifier("do_something"))
    'DoSomething'

    >>> method_name(Identifier("do_something_to_URL"))
    'DoSomethingToUrl'
    """
    return naming.capitalized_camel_case(identifier)


def function_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a function from its meta-model ``identifier``.

    >>> function_name(Identifier("do_something"))
    'DoSomething'

    >>> function_name(Identifier("do_something_to_URL"))
    'DoSomethingToUrl'
    """
    return naming.capitalized_camel_case(identifier)


def argument_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for an argument based on its meta-model ``identifier``.

    >>> argument_name(Identifier("something"))
    'something'

    >>> argument_name(Identifier("something_to_URL"))
    'something_to_url'

    >>> argument_name(Identifier("void"))
    'voiD'

    >>> argument_name(Identifier("static_assert"))
    'static_asserT'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return naming.lower_snake_case(identifier)


def variable_name(identifier: Identifier) -> Identifier:
    """
    Generate a C++ name for a variable based on its meta-model ``identifier``.

    >>> variable_name(Identifier("something"))
    'something'

    >>> variable_name(Identifier("something_to_URL"))
    'something_to_url'

    >>> variable_name(Identifier("void"))
    'voiD'

    >>> variable_name(Identifier("static_assert"))
    'static_asserT'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return naming.lower_snake_case(identifier)


def constant_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a constant based on its meta-model ``identifier``.

    >>> constant_name(Identifier("something"))
    'kSomething'

    >>> constant_name(Identifier("URL_to_something"))
    'kUrlToSomething'
    """
    return Identifier(f"k{naming.capitalized_camel_case(identifier)}")
