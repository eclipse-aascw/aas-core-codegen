# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Generate C# identifiers based on the identifiers from the meta-model."""
from typing import Union, Final, FrozenSet

from icontract import require

import aas_core_codegen.naming
from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, assert_never

_KEYWORD_SET: Final[FrozenSet[Identifier]] = frozenset(
    {
        Identifier("abstract"),
        Identifier("as"),
        Identifier("base"),
        Identifier("bool"),
        Identifier("break"),
        Identifier("byte"),
        Identifier("case"),
        Identifier("catch"),
        Identifier("char"),
        Identifier("checked"),
        Identifier("class"),
        Identifier("const"),
        Identifier("continue"),
        Identifier("decimal"),
        Identifier("default"),
        Identifier("delegate"),
        Identifier("do"),
        Identifier("double"),
        Identifier("else"),
        Identifier("enum"),
        Identifier("event"),
        Identifier("explicit"),
        Identifier("extern"),
        Identifier("false"),
        Identifier("finally"),
        Identifier("fixed"),
        Identifier("float"),
        Identifier("for"),
        Identifier("foreach"),
        Identifier("goto"),
        Identifier("if"),
        Identifier("implicit"),
        Identifier("in"),
        Identifier("int"),
        Identifier("interface"),
        Identifier("internal"),
        Identifier("is"),
        Identifier("lock"),
        Identifier("long"),
        Identifier("namespace"),
        Identifier("new"),
        Identifier("null"),
        Identifier("object"),
        Identifier("operator"),
        Identifier("out"),
        Identifier("override"),
        Identifier("params"),
        Identifier("private"),
        Identifier("protected"),
        Identifier("public"),
        Identifier("readonly"),
        Identifier("ref"),
        Identifier("return"),
        Identifier("sbyte"),
        Identifier("sealed"),
        Identifier("short"),
        Identifier("sizeof"),
        Identifier("stackalloc"),
        Identifier("static"),
        Identifier("string"),
        Identifier("struct"),
        Identifier("switch"),
        Identifier("this"),
        Identifier("throw"),
        Identifier("true"),
        Identifier("try"),
        Identifier("typeof"),
        Identifier("uint"),
        Identifier("ulong"),
        Identifier("unchecked"),
        Identifier("unsafe"),
        Identifier("ushort"),
        Identifier("using"),
        Identifier("virtual"),
        Identifier("void"),
        Identifier("volatile"),
        Identifier("while"),
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

assert all(not keyword.startswith("_") for keyword in _KEYWORD_SET), (
    "We expected all the keywords to not start with ``_``, since that was "
    "the assumption when we renamed them to avoid conflicts, "
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
    """
    Generate a C# interface name based on its meta-model ``identifier``.

    >>> interface_name(Identifier("something"))
    'ISomething'

    >>> interface_name(Identifier("URL_to_something"))
    'IUrlToSomething'
    """
    return Identifier(f"I{aas_core_codegen.naming.capitalized_camel_case(identifier)}")


def enum_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for an enum based on its meta-model ``identifier``.

    >>> enum_name(Identifier("something"))
    'Something'

    >>> enum_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def enum_literal_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for an enum literal based on its meta-model ``identifier``.

    >>> enum_literal_name(Identifier("something"))
    'Something'

    >>> enum_literal_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def class_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for a class based on its meta-model ``identifier``.

    >>> class_name(Identifier("something"))
    'Something'

    >>> class_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def name_of(
    something: Union[
        intermediate.Enumeration, intermediate.ConcreteClass, intermediate.Interface
    ]
) -> Identifier:
    """Dispatch to the appropriate naming function."""
    if isinstance(something, intermediate.Enumeration):
        return enum_name(something.name)

    elif isinstance(something, intermediate.ConcreteClass):
        return class_name(something.name)

    elif isinstance(something, intermediate.Interface):
        return interface_name(something.name)

    else:
        assert_never(something)


def _rename_to_avoid_type_name_clash(identifier: Identifier) -> Identifier:
    """
    Rename the ``identifier`` so that it differs from the enclosing type name.

    >>> _rename_to_avoid_type_name_clash(Identifier("Something"))
    'Something_'
    """
    return Identifier(f"{identifier}_")


def property_name(prop: intermediate.Property) -> Identifier:
    """
    Generate a C# name for the public property ``prop`` of a class.

    C# forbids a member to have the same name as its enclosing type, so we add
    an underscore suffix to such a property. We look at the class which specifies
    the property so that all its descendants agree on the name.
    """
    prop_name = aas_core_codegen.naming.capitalized_camel_case(prop.name)

    if class_name(prop.specified_for.name) == prop_name:
        return Identifier(f"{prop_name}_")

    return prop_name


def static_property_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for a static property based on its meta-model ``identifier``.

    >>> static_property_name(Identifier("something"))
    'Something'

    >>> static_property_name(Identifier("something_to_URL"))
    'SomethingToUrl'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def private_property_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for a private property based on the ``identifier``.

    >>> private_property_name(Identifier("something"))
    '_something'

    >>> private_property_name(Identifier("something_to_URL"))
    '_somethingToUrl'
    """
    return Identifier(f"_{aas_core_codegen.naming.lower_camel_case(identifier)}")


def private_method_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for a private method based on the ``identifier``.

    >>> private_method_name(Identifier("something"))
    '_something'

    >>> private_method_name(Identifier("something_to_URL"))
    '_somethingToUrl'
    """
    return Identifier(f"_{aas_core_codegen.naming.lower_camel_case(identifier)}")


def method_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for a member method based on its meta-model ``identifier``.

    >>> method_name(Identifier("do_something"))
    'DoSomething'

    >>> method_name(Identifier("do_something_to_URL"))
    'DoSomethingToUrl'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def argument_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for an argument based on its meta-model ``identifier``.

    >>> argument_name(Identifier("something"))
    'something'

    >>> argument_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> argument_name(Identifier("interface"))
    'interfacE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def variable_name(identifier: Identifier) -> Identifier:
    """
    Generate a C# name for a variable based on its meta-model ``identifier``.

    >>> variable_name(Identifier("something"))
    'something'

    >>> variable_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> variable_name(Identifier("interface"))
    'interfacE'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)
