# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Provide functions shared among the tests."""
from typing import Tuple, Optional, Mapping

import aas_core_codegen.common
import tests.common
from aas_core_codegen import intermediate, infer_for_schema
from aas_core_codegen.common import Identifier


def parse_to_symbol_table_and_something_cls(
    source: str,
) -> Tuple[intermediate.SymbolTable, intermediate.ClassUnion]:
    """
    Parse the ``source``.

    Return the symbol table and our type corresponding to the class ``Something``
    in the ``source``.
    """
    symbol_table, error = tests.common.translate_source_to_intermediate(source=source)
    assert error is None, tests.common.most_underlying_messages(error)
    assert symbol_table is not None
    something_cls = symbol_table.must_find_class(Identifier("Something"))

    return symbol_table, something_cls


def parse_to_symbol_table_and_something_cls_and_constraints_by_class(
    source: str,
) -> Tuple[
    intermediate.SymbolTable,
    intermediate.ClassUnion,
    Mapping[intermediate.ClassUnion, infer_for_schema.ConstraintsByValue],
]:
    """
    Parse the ``source``.

    Return the symbol table and our type corresponding to the class ``Something``
    in the ``source`` as well as the inferred constraints mapped by classes.
    """
    symbol_table, something_cls = parse_to_symbol_table_and_something_cls(source=source)

    constraints_by_class, error = infer_for_schema.infer_constraints_by_class(
        symbol_table=symbol_table
    )
    assert error is None, tests.common.most_underlying_messages(error)
    assert constraints_by_class is not None

    return symbol_table, something_cls, constraints_by_class


def select_constraints_of_property(
    cls: intermediate.ClassUnion,
    property_name: str,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
) -> Optional[infer_for_schema.Constraints]:
    """Get the constraints for the given property of the class ``cls``."""
    constraints_by_value = constraints_by_class.get(cls, None)

    if constraints_by_value is None:
        raise ValueError(
            f"Class {cls.name!r} is not included in the supplied constraints-by-class."
        )

    if aas_core_codegen.common.IDENTIFIER_RE.match(property_name) is None:
        raise ValueError(f"Supplied invalid property name {property_name!r}")

    prop = cls.properties_by_name.get(Identifier(property_name), None)
    if prop is None:
        raise ValueError(
            f"The property {property_name!r} does not exist in class {cls.name!r}"
        )

    return constraints_by_value.get(
        intermediate.beneath_optional(prop.type_annotation), None
    )
