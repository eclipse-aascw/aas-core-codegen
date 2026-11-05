# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""
Generate identifiers internal to an XML Schema Definition (XSD).

The identifiers are based on the meta-model. Unlike
:py:mod:`aas_core_codegen.naming`, which are used with different generators,
these identifiers are used only for the XSD.
"""
from aas_core_codegen.common import Identifier


def type_name(identifier: Identifier) -> Identifier:
    """
    Generate the XML type name for the given class based on its ``identifier``.

    >>> type_name(Identifier("something"))
    'something_t'

    >>> type_name(Identifier("URL_to_something"))
    'urlToSomething_t'
    """
    parts = identifier.split("_")
    assert (
        len(parts) >= 1
    ), f"Expected at least one part for the valid identifier: {identifier}"

    if len(parts) == 1:
        return Identifier(f"{parts[0].lower()}_t")

    return Identifier(
        "{}{}_t".format(
            parts[0].lower(), "".join(part.capitalize() for part in parts[1:])
        )
    )


def group_name(identifier: Identifier) -> Identifier:
    """
    Generate the XML group name for the given class based on its ``identifier``.

    >>> group_name(Identifier("something"))
    'something'

    >>> group_name(Identifier("URL_to_something"))
    'urlToSomething'
    """
    parts = identifier.split("_")
    assert (
        len(parts) >= 1
    ), f"Expected at least one part for the valid identifier: {identifier}"

    if len(parts) == 1:
        return Identifier(f"{parts[0].lower()}")

    return Identifier(
        "{}{}".format(
            parts[0].lower(), "".join(part.capitalize() for part in parts[1:])
        )
    )


def choice_group_name(identifier: Identifier) -> Identifier:
    """
    Generate the XML group name for the interface of the given class ``identifier``.

    >>> choice_group_name(Identifier("something"))
    'something_choice'

    >>> choice_group_name(Identifier("URL_to_something"))
    'urlToSomething_choice'
    """
    parts = identifier.split("_")
    assert (
        len(parts) >= 1
    ), f"Expected at least one part for the valid identifier: {identifier}"

    if len(parts) == 1:
        return Identifier(f"{parts[0].lower()}_choice")

    return Identifier(
        "{}{}_choice".format(
            parts[0].lower(), "".join(part.capitalize() for part in parts[1:])
        )
    )
