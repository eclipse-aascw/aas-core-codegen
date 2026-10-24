"""Understand the hierarchy of classes in the symbol table as an ontology."""
from typing import (
    Sequence,
    Optional,
    Set,
    Final,
    Mapping,
    MutableMapping,
    List,
    cast,
    Tuple,
)

import sortedcontainers
from icontract import require, ensure

from aas_core_codegen import parse
from aas_core_codegen.common import Error, Identifier


def first_not_in_topological_order(
    classes: Sequence[parse.Class], parsed_symbol_table: parse.SymbolTable
) -> Optional[parse.Class]:
    """
    Verify that ``classes`` are topologically sorted.

    :return: The first class which is not fitting the expected order.
    """
    observed: Set[parse.Class] = set()
    for cls in classes:
        for parent_name in cls.inheritances:
            # We ignore here the initial set of the constrained primitives.
            if parent_name in parse.PRIMITIVE_TYPES:
                assert len(cls.inheritances) == 1, (
                    f"A constrained primitive type in the initial set should only "
                    f"inherit from the primitive type. {cls.name=}"
                )
                continue

            parent = parsed_symbol_table.must_find_class(parent_name)
            if parent not in observed:
                return cls

        observed.add(cls)

    return None


class _UnverifiedOntology:
    """
    Provide an ontology computed from a symbol table.

    This private is explicitly made protected to signal that it has not been vetted
    yet and might be inconsistent. For example, there might be classes which have
    conflicting properties or methods with their ancestors.
    """

    #: Topologically sorted classes
    classes: Final[Sequence[parse.Class]]

    #: Map class 🠒 topologically sorted ancestors
    _ancestors_of: Final[Mapping[parse.Class, Sequence[parse.Class]]]

    _descendants_of: Final[Mapping[parse.Class, Sequence[parse.Class]]]

    # fmt: off
    @require(
        lambda classes, parsed_symbol_table:
        first_not_in_topological_order(classes, parsed_symbol_table) is None
    )
    @require(
        lambda classes:
        len(classes) == 0
        or sum(
            1
            for inheritance in classes[0].inheritances
            if inheritance not in parse.PRIMITIVE_TYPES
        ) == 0,
        "Origins first",
    )
    @require(
        lambda classes: len(set(classes)) == len(classes),
        "Unique classes in the topological sort",
    )
    @ensure(
        lambda self:
        all(
            self.can_list_descendants(cls)
            for cls in self.classes
        ),
        "The descendants` defined for all classes"
    )
    @ensure(
        lambda self:
        all(
            self.can_list_ancestors(cls)
            for cls in self.classes
        ),
        "The ancestors defined for all classes"
    )
    @ensure(
        lambda self, parsed_symbol_table: all(
            first_not_in_topological_order(
                class_ancestors, parsed_symbol_table) is None
            for class_ancestors in self._ancestors_of.values()
        )
    )
    # fmt: on
    def __init__(
        self, classes: Sequence[parse.Class], parsed_symbol_table: parse.SymbolTable
    ) -> None:
        """Initialize with the given values and pre-compute the ancestors."""
        self.classes = classes

        # region Determine ancestors

        ancestors_of: MutableMapping[parse.Class, List[parse.Class]] = dict()

        order_of = {cls: i for i, cls in enumerate(classes)}

        for cls in classes:
            if any(
                parent_name in parse.PRIMITIVE_TYPES for parent_name in cls.inheritances
            ):
                assert len(cls.inheritances) == 1, (
                    f"A constrained primitive type in the initial set should only "
                    f"inherit from the primitive type. {cls.name=}"
                )
                ancestors_of[cls] = []

                continue

            parents = [
                parsed_symbol_table.must_find_class(parent_name)
                for parent_name in cls.inheritances
            ]

            parents_with_order = [(order_of[parent], parent) for parent in parents]

            sorted_parents = sorted(parents_with_order, key=lambda item: item[0])

            class_ancestors: List[parse.Class] = []
            for _, parent in sorted_parents:
                assert parent in ancestors_of, (
                    f"Expected to process all the parent's of the class {cls.name} "
                    f"before (due to topological sort), "
                    f"but the parent class {parent.name} has not been processed"
                )

                class_ancestors.extend(ancestors_of[parent])

                class_ancestors.append(parent)

            ancestors_of[cls] = class_ancestors

        self._ancestors_of = ancestors_of

        # endregion

        # region Determine descendants

        descendants_of: MutableMapping[parse.Class, List[parse.Class]] = dict()

        # Simply inverse

        for cls in self.classes:
            descendants_of[cls] = []

        for cls, ancestors in ancestors_of.items():
            for ancestor in ancestors:
                descendants_of[ancestor].append(cls)

        self._descendants_of = descendants_of

        # endregion

    def can_list_ancestors(self, cls: parse.Class) -> bool:
        """Return ``True`` if there is a record of the ``cls``'s ancestors."""
        return cls in self._ancestors_of

    def list_ancestors(self, cls: parse.Class) -> Sequence[parse.Class]:
        """Retrieve the ancestors of the given class ``cls``."""
        result = self._ancestors_of.get(cls, None)
        if result is None:
            raise KeyError(
                f"The ancestors of the class {cls} have not been precomputed."
            )

        return result

    def can_list_descendants(self, cls: parse.Class) -> bool:
        """Return ``True`` if there is a record of the ``cls``'s descendants."""
        return cls in self._descendants_of

    def list_descendants(self, cls: parse.Class) -> Sequence[parse.Class]:
        """Retrieve the descendants of the given class ``cls``."""

        result = self._descendants_of.get(cls, None)
        if result is None:
            raise KeyError(
                f"The descendants of the class {cls} have not been precomputed."
            )

        return result


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _topologically_sort(
    parsed_symbol_table: parse.SymbolTable,
) -> Tuple[Optional[_UnverifiedOntology], Optional[parse.Class]]:
    """
    Sort topologically all the classes in the ``parsed_symbol_table``.

    :return: topologically sorted classes, or a class in a cycle
    """
    # See https://en.wikipedia.org/wiki/Topological_sorting#Depth-first%20search
    # We use sorted containers to avoid non-deterministic behavior.

    result: List[parse.Class] = []

    without_permanent_marks: sortedcontainers.SortedSet[
        parse.Class
    ] = sortedcontainers.SortedSet(key=lambda a_class: a_class.name)

    for our_type in parsed_symbol_table.our_types:
        if not isinstance(our_type, parse.Class):
            continue

        without_permanent_marks.add(our_type)

    permanent_marks: sortedcontainers.SortedSet[
        parse.Class
    ] = sortedcontainers.SortedSet(key=lambda a_class: a_class.name)

    temporary_marks: sortedcontainers.SortedSet[
        parse.Class
    ] = sortedcontainers.SortedSet(key=lambda a_class: a_class.name)

    visited_more_than_once: Optional[parse.Class] = None

    def visit(cls: parse.Class) -> None:
        nonlocal visited_more_than_once
        nonlocal result

        if visited_more_than_once:
            return

        if cls in permanent_marks:
            return

        if cls in temporary_marks:
            visited_more_than_once = cls
            return

        temporary_marks.add(cls)

        for an_identifier in cls.inheritances:
            # We ignore the primitive types from which constrained primitive types
            # inherit.
            if an_identifier in parse.PRIMITIVE_TYPES:
                continue

            another_cls = parsed_symbol_table.must_find_class(an_identifier)

            visit(cls=another_cls)

        temporary_marks.remove(cls)
        permanent_marks.add(cls)

        if cls in without_permanent_marks:
            without_permanent_marks.remove(cls)

        result.append(cls)

    while len(without_permanent_marks) > 0 and not visited_more_than_once:
        visit(without_permanent_marks[0])

    if visited_more_than_once:
        return None, visited_more_than_once

    return (
        _UnverifiedOntology(classes=result, parsed_symbol_table=parsed_symbol_table),
        None,
    )


class Ontology(_UnverifiedOntology):
    """
    Provide an ontology computed from a symbol table.

    The ontology has been verified through :py:func:`map_symbol_table_to_ontology`.
    """


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def map_symbol_table_to_ontology(
    parsed_symbol_table: parse.SymbolTable,
) -> Tuple[Optional[Ontology], Optional[List[Error]]]:
    """Infer the ontology of the classes from the ``parsed_symbol_table``."""
    ontology, visited_more_than_once = _topologically_sort(
        parsed_symbol_table=parsed_symbol_table
    )
    if visited_more_than_once is not None:
        return (
            None,
            [
                Error(
                    visited_more_than_once.node,
                    f"Expected no cycles in the inheritance, "
                    f"but the class {visited_more_than_once.name} has been observed "
                    f"in a cycle",
                )
            ],
        )

    assert ontology is not None

    errors: List[Error] = []

    # region Check that properties and methods do not conflict among ancestors

    for our_type in parsed_symbol_table.our_types:
        if not isinstance(our_type, parse.Class):
            continue

        ancestors = ontology.list_ancestors(cls=our_type)

        observed_properties: MutableMapping[str, parse.Class] = dict()
        observed_methods: MutableMapping[str, parse.Class] = dict()

        for ancestor in ancestors:
            for prop in ancestor.properties:
                if prop.name not in observed_properties:
                    observed_properties[prop.name] = ancestor

            for method in ancestor.methods:
                if method.name not in observed_properties:
                    observed_methods[method.name] = ancestor

        for prop in our_type.properties:
            if prop.name in observed_properties:
                errors.append(
                    Error(
                        prop.node,
                        f"The property has already been defined in the ancestor "
                        f"class {observed_properties[prop.name].name}: {prop.name}",
                    )
                )

        for method in our_type.methods:
            if method.name == "__init__":
                continue

            if method.name in observed_methods:
                errors.append(
                    Error(
                        method.node,
                        f"The method has already been defined in the ancestor "
                        f"class {observed_methods[method.name].name}: {method.name}",
                    )
                )

    # endregion

    # region Check that ancestors do not have constructors if the class lacks one

    for our_type in parsed_symbol_table.our_types:
        if not isinstance(our_type, parse.Class):
            continue

        if "__init__" not in our_type.methods_by_name:
            for ancestor in ontology.list_ancestors(our_type):
                ancestor_init = ancestor.methods_by_name.get(
                    Identifier("__init__"), None
                )

                if ancestor_init is not None and len(ancestor_init.arguments) > 1:
                    argument_names_str = ", ".join(
                        arg.name for arg in ancestor_init.arguments
                    )

                    errors.append(
                        Error(
                            our_type.node,
                            f"The class {our_type.name} does not specify "
                            f"a constructor, but the ancestor class "
                            f"{ancestor.name} specifies a constructor with "
                            f"arguments: {argument_names_str}",
                        )
                    )

    # endregion

    if len(errors) > 0:
        return None, errors

    return cast(Ontology, ontology), None
