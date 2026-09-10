"""Generate Python identifiers based on the identifiers from the meta-model."""
from typing import Union

from icontract import require

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, assert_never


# fmt: off
@require(
    lambda identifier: identifier[0].isupper(),
    "Enumeration name must start with a capital letter"
)
# fmt: on
def enum_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an enum based on its meta-model ``identifier``.

    >>> enum_name(Identifier("Something"))
    'Something'

    >>> enum_name(Identifier("URL_to_something"))
    'URLToSomething'

    >>> enum_name(Identifier("Something_to_URL"))
    'SomethingToURL'
    """
    parts = identifier.split("_")

    return Identifier(
        "".join(part if part.upper() == part else part.capitalize() for part in parts)
    )


# fmt: off
@require(
    lambda identifier:
    identifier[0].isupper(),
    "Class names must start with a capital letter"
)
# fmt: on
def class_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a class based on its meta-model ``identifier``.

    >>> class_name(Identifier("Something"))
    'Something'

    >>> class_name(Identifier("URL_to_something"))
    'URLToSomething'

    >>> class_name(Identifier("Something_to_URL"))
    'SomethingToURL'
    """
    parts = identifier.split("_")

    return Identifier(
        "".join(part if part == part.upper() else part.capitalize() for part in parts)
    )


def union_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a named union based on its meta-model ``identifier``.

    A named union is represented as a ``Union[...]`` type alias, so it follows
    the same convention as :py:func:`class_name`, but is kept as a separate
    function since a named union is conceptually distinct from a class.

    >>> union_name(Identifier("Something"))
    'Something'

    >>> union_name(Identifier("URL_to_something"))
    'URLToSomething'

    >>> union_name(Identifier("Something_to_URL"))
    'SomethingToURL'
    """
    parts = identifier.split("_")

    return Identifier(
        "".join(part if part == part.upper() else part.capitalize() for part in parts)
    )


def name_of(
    something: Union[
        intermediate.Enumeration,
        intermediate.AbstractClass,
        intermediate.ConcreteClass,
        intermediate.NamedUnion,
    ]
) -> Identifier:
    """Dispatch the name based on the run-time type of ``something``."""
    if isinstance(something, intermediate.Enumeration):
        return enum_name(something.name)

    elif isinstance(
        something, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ):
        return class_name(something.name)

    elif isinstance(something, intermediate.NamedUnion):
        return union_name(something.name)

    else:
        assert_never(something)


def enum_literal_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an enum literal based on its meta-model ``identifier``.

    >>> enum_literal_name(Identifier("something"))
    'SOMETHING'

    >>> enum_literal_name(Identifier("URL_to_something"))
    'URL_TO_SOMETHING'
    """
    return naming.upper_snake_case(identifier)


def private_constant_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a constant based on its meta-model ``identifier``.

    >>> private_constant_name(Identifier("something"))
    '_SOMETHING'

    >>> private_constant_name(Identifier("URL_to_something"))
    '_URL_TO_SOMETHING'
    """
    return Identifier(f"_{naming.upper_snake_case(identifier)}")


def constant_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a constant based on its meta-model ``identifier``.

    >>> constant_name(Identifier("something"))
    'SOMETHING'

    >>> constant_name(Identifier("URL_to_something"))
    'URL_TO_SOMETHING'
    """
    return naming.upper_snake_case(identifier)


# fmt: off
@require(
    lambda identifier:
    identifier[0].isupper(),
    "Class names must start with a capital letter"
)
# fmt: on
def private_class_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a priave class based on its meta-model ``identifier``.

    >>> private_class_name(Identifier("Something"))
    '_Something'

    >>> private_class_name(Identifier("URL_to_something"))
    '_URLToSomething'
    """
    parts = identifier.split("_")

    return Identifier(
        "_"
        + "".join(part if part.upper() == part else part.capitalize() for part in parts)
    )


def property_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a public property based on its meta-model ``identifier``.

    >>> property_name(Identifier("something"))
    'something'

    >>> property_name(Identifier("something_to_URL"))
    'something_to_url'

    >>> property_name(Identifier("URL_to_something"))
    'url_to_something'
    """
    return naming.lower_snake_case(identifier)


def private_property_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a private property based on the ``identifier``.

    >>> private_property_name(Identifier("something"))
    '_something'

    >>> private_property_name(Identifier("something_to_URL"))
    '_something_to_url'

    >>> private_property_name(Identifier("URL_to_something"))
    '_url_to_something'
    """
    return Identifier(f"_{naming.lower_snake_case(identifier)}")


def private_method_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a private method based on the ``identifier``.

    >>> private_method_name(Identifier("something"))
    '_something'

    >>> private_method_name(Identifier("something_to_URL"))
    '_something_to_url'

    >>> private_method_name(Identifier("URL_to_something"))
    '_url_to_something'
    """
    return Identifier(f"_{naming.lower_snake_case(identifier)}")


def private_function_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a private function from its meta-model ``identifier``.

    >>> private_function_name(Identifier("do_something"))
    '_do_something'

    >>> private_function_name(Identifier("do_something_to_URL"))
    '_do_something_to_url'
    """
    return Identifier(f"_{naming.lower_snake_case(identifier)}")


def function_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a function from its meta-model ``identifier``.

    >>> function_name(Identifier("do_something"))
    'do_something'

    >>> function_name(Identifier("do_something_to_URL"))
    'do_something_to_url'
    """
    return naming.lower_snake_case(identifier)


def method_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an instance method based on its meta-model ``identifier``.

    >>> method_name(Identifier("do_something"))
    'do_something'

    >>> method_name(Identifier("do_something_to_URL"))
    'do_something_to_url'
    """
    return naming.lower_snake_case(identifier)


def argument_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an argument based on its meta-model ``identifier``.

    >>> argument_name(Identifier("something"))
    'something'

    >>> argument_name(Identifier("something_to_URL"))
    'something_to_url'
    """
    return naming.lower_snake_case(identifier)


def variable_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a variable based on its meta-model ``identifier``.

    >>> variable_name(Identifier("something"))
    'something'

    >>> variable_name(Identifier("something_to_URL"))
    'something_to_url'
    """
    return naming.lower_snake_case(identifier)
