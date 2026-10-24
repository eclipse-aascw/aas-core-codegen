"""Generate names from ``Our_identifier_snake_case`` to other cases."""

from typing import List

from icontract import ensure, require

from aas_core_codegen.common import Identifier


def lower_snake_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``lower_snake_case``."""
    parts = identifier.split("_")

    assert len(parts) > 0, "Expected at least one part in the identifier"

    return Identifier("_".join(part.lower() for part in parts))


def upper_snake_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``UPPER_SNAKE_CASE``."""
    parts = identifier.split("_")

    assert len(parts) > 0, "Expected at least one part in the identifier"

    return Identifier("_".join(part.upper() for part in parts))


def lower_camel_case(identifier: Identifier) -> Identifier:
    """
    Convert the identifier to a ``camelCase``.

    The leading underscores, which signal the visibility in the meta-model, are
    stripped.

    >>> lower_camel_case(Identifier("do_something"))
    'doSomething'

    >>> lower_camel_case(Identifier("_do_something"))
    'doSomething'
    """
    parts = identifier.lstrip("_").split("_")

    assert len(parts) > 0, "Expected at least one part in the identifier"

    if len(parts) == 1:
        return Identifier(parts[0].lower())

    cased_parts: List[str] = []

    iterator = iter(parts)
    first_part = next(iterator)
    cased_parts.append(first_part.lower())

    for part in iterator:
        cased_parts.append(part.capitalize())

    return Identifier("".join(cased_parts))


def capitalized_camel_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``CamelCase``."""
    parts = identifier.split("_")
    return Identifier("".join(part.capitalize() for part in parts))


def json_property(identifier: Identifier) -> Identifier:
    """
    Generate a JSON name of a property based on its meta-model ``identifier``.

    >>> json_property(Identifier("something"))
    'something'

    >>> json_property(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> json_property(Identifier("global_asset_ID"))
    'globalAssetId'

    >>> json_property(Identifier("specific_asset_IDs"))
    'specificAssetIds'
    """
    return lower_camel_case(identifier)


# fmt: off
@require(
    lambda identifier: identifier[0].isupper(),
    "The class name must start with a capital letter"
)
@ensure(
    lambda result: "_" not in result
) # This post-condition avoids naming conflicts with prefixing in the JSON schema.
@ensure(
    lambda result: '"' not in result and "'" not in result and '\\' not in result
    # This post-condition simplifies a lot of generator code since we can simply in-line
    # the model type in strings.
)
# fmt: on
def json_model_type(identifier: Identifier) -> Identifier:
    """
    Generate the ``modelType`` of the class based on its meta-model ``identifier``.

    >>> json_model_type(Identifier("Something"))
    'Something'

    >>> json_model_type(Identifier("Data_type_IEC_61360"))
    'DataTypeIec61360'

    >>> json_model_type(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return capitalized_camel_case(identifier)


# fmt: off
@require(
    lambda identifier: identifier[0].upper() == identifier[0],
    "The class name must start with a capital letter"
)
# fmt: on
def xml_class_name(identifier: Identifier) -> Identifier:
    """
    Generate the XML tag name for the given class based on its ``identifier``.

    >>> xml_class_name(Identifier("Something"))
    'something'

    >>> xml_class_name(Identifier("URL_to_something"))
    'urlToSomething'
    """
    return lower_camel_case(identifier)


def xml_property(identifier: Identifier) -> Identifier:
    """
    Generate the XML name for the given property based on its ``identifier``.

    >>> xml_property(Identifier("something"))
    'something'

    >>> xml_property(Identifier("URL_to_something"))
    'urlToSomething'
    """
    return lower_camel_case(identifier)
