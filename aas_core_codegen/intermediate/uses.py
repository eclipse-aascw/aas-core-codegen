"""
Check which constructs the meta-model uses.

The generators use these checks to generate the helpers, the includes and
the tests only if the meta-model needs them.

Import this module as ``intermediate_uses`` so that the checks read naturally,
*e.g.*, ``intermediate_uses.modulo(symbol_table)``.
"""

import itertools
from typing import Iterator, List, Mapping, Sequence, Set, Tuple, Union

from aas_core_codegen.intermediate import (
    _types,
    type_inference as intermediate_type_inference,
)
from aas_core_codegen.parse import tree as parse_tree


def json_types(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether any property in the model refers to a JSON-able type.

    This works recursively: a JSON-able type is picked up regardless of how
    deeply it is nested within a property's type annotation (*e.g.*, inside
    a ``List[...]`` or an ``Optional[...]``), not just when the property
    itself is directly annotated as one.
    """
    for cls in symbol_table.classes:
        for prop in cls.properties:
            for type_anno in _types.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if isinstance(
                    type_anno,
                    (
                        _types.JsonValueTypeAnnotation,
                        _types.JsonArrayTypeAnnotation,
                        _types.JsonObjectTypeAnnotation,
                    ),
                ):
                    return True

    return False


def _over_transpilable_nodes(
    symbol_table: _types.SymbolTable,
) -> Iterator[parse_tree.Node]:
    """
    Iterate recursively over all the nodes which the generators transpile.

    These are the nodes of the invariants, of the transpilable verification
    functions and of the understood methods.
    """
    for our_type in symbol_table.our_types:
        if isinstance(
            our_type,
            (_types.ConstrainedPrimitive, _types.AbstractClass, _types.ConcreteClass),
        ):
            for an_invariant in our_type.invariants:
                # NOTE (mristin):
                # We skip the inherited invariants as they are also listed in
                # the type which specified them.
                if an_invariant.specified_for is not our_type:
                    continue

                yield from parse_tree.over_nodes(an_invariant.body)

        if isinstance(our_type, (_types.AbstractClass, _types.ConcreteClass)):
            for method in our_type.methods:
                if isinstance(method, _types.UnderstoodMethod):
                    for node in method.body:
                        yield from parse_tree.over_nodes(node)

    for verification in symbol_table.verification_functions:
        if isinstance(verification, _types.TranspilableVerification):
            for node in verification.parsed.body:
                yield from parse_tree.over_nodes(node)


def modulo(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether the meta-model uses the modulo operator in transpilable code.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for the modulo.
    """
    return any(
        isinstance(node, parse_tree.Mod)
        for node in _over_transpilable_nodes(symbol_table)
    )


def _over_inferred_nodes(
    type_inference: intermediate_type_inference.TypeInference,
) -> Iterator[
    Tuple[
        parse_tree.Node,
        Mapping[parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion],
    ]
]:
    """
    Iterate over all the nodes of the transpilable code along their type maps.

    Each invariant, verification function and understood method is inferred only
    once, so we visit each node only once.
    """
    roots_and_type_maps = itertools.chain(
        (
            ([invariant.body], inference.type_map)
            for invariant, inference in type_inference.by_invariant.items()
        ),
        (
            (verification.parsed.body, inference.type_map)
            for verification, inference in type_inference.by_verification.items()
        ),
        (
            (method.body, inference.type_map)
            for method, inference in type_inference.by_method.items()
        ),
    )

    for roots, type_map in roots_and_type_maps:
        for root in roots:
            for node in parse_tree.over_nodes(root):
                yield node, type_map


def _orders(
    type_inference: intermediate_type_inference.TypeInference,
    primitive_type: intermediate_type_inference.PrimitiveType,
) -> bool:
    """
    Check whether any transpiled code orders two values of ``primitive_type``.

    We look for the comparisons ``<``, ``<=``, ``>`` and ``>=``. The operands of
    a comparison share the primitive type, so we only check the left one.
    """
    return any(
        isinstance(node, parse_tree.Comparison)
        and node.op not in (parse_tree.Comparator.EQ, parse_tree.Comparator.NE)
        and intermediate_type_inference.try_primitive_type(type_map[node.left])
        is primitive_type
        for node, type_map in _over_inferred_nodes(type_inference)
    )


def _calls_builtin_method(
    type_inference: intermediate_type_inference.TypeInference,
    method: intermediate_type_inference.BuiltinMethod,
) -> bool:
    """Check whether any transpiled code calls the built-in ``method``."""
    for node, type_map in _over_inferred_nodes(type_inference):
        if not isinstance(node, parse_tree.MethodCall):
            continue

        member_type = type_map[node.member]
        if (
            isinstance(
                member_type, intermediate_type_inference.BuiltinMethodTypeAnnotation
            )
            and member_type.method is method
        ):
            return True

    return False


def string_len_call(
    type_inference: intermediate_type_inference.TypeInference,
) -> bool:
    """
    Check whether any transpiled code takes ``len`` of a string.

    We look beneath the optional, since the transpilers unwrap a narrowed
    optional string before they take its length.
    """
    return any(
        isinstance(node, parse_tree.FunctionCall)
        and node.name.identifier == "len"
        and len(node.args) == 1
        and intermediate_type_inference.try_primitive_type(
            intermediate_type_inference.beneath_optional(type_map[node.args[0]])
        )
        is intermediate_type_inference.PrimitiveType.STR
        for node, type_map in _over_inferred_nodes(type_inference)
    )


def string_slicing(type_inference: intermediate_type_inference.TypeInference) -> bool:
    """
    Check whether any transpiled code slices a string.

    We look beneath the optional for the same reason as in
    :py:func:`string_len_call`.
    """
    return any(
        isinstance(node, parse_tree.Slice)
        and intermediate_type_inference.try_primitive_type(
            intermediate_type_inference.beneath_optional(type_map[node.collection])
        )
        is intermediate_type_inference.PrimitiveType.STR
        for node, type_map in _over_inferred_nodes(type_inference)
    )


def string_find_call(type_inference: intermediate_type_inference.TypeInference) -> bool:
    """Check whether any transpiled code calls ``str.find``."""
    return _calls_builtin_method(type_inference, intermediate_type_inference.STR_FIND)


def string_ordering(type_inference: intermediate_type_inference.TypeInference) -> bool:
    """
    Check whether any transpiled code orders two strings.

    The targets use this check to generate the helper for comparing the strings
    only if the meta-model needs it. The helper orders the strings by their
    characters (code points) as Python does, since Python is the language of
    the meta-model specifications.
    """
    return _orders(type_inference, intermediate_type_inference.PrimitiveType.STR)


def bool_ordering(type_inference: intermediate_type_inference.TypeInference) -> bool:
    """
    Check whether any transpiled code orders two booleans.

    The targets which do not order the booleans natively use this check to
    generate their helper only if the meta-model needs it.
    """
    return _orders(type_inference, intermediate_type_inference.PrimitiveType.BOOL)


def assert_statements_in(
    functions: Sequence[Union[_types.Verification, _types.Method]],
) -> bool:
    """
    Check whether the bodies of the ``functions`` contain ``assert`` statements.

    The C++ generator uses this check to include ``<stdexcept>`` only where
    it is needed.
    """
    for function in functions:
        body: Sequence[parse_tree.Node] = ()
        if isinstance(function, _types.TranspilableVerification):
            body = function.parsed.body
        elif isinstance(function, _types.UnderstoodMethod):
            body = function.body
        else:
            pass

        if any(
            isinstance(node, parse_tree.Assert)
            for stmt in body
            for node in parse_tree.over_nodes(stmt)
        ):
            return True

    return False


def abs_call(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether the meta-model calls the built-in ``abs`` in transpilable code.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for ``abs``.
    """
    return any(
        isinstance(node, parse_tree.FunctionCall) and node.name.identifier == "abs"
        for node in _over_transpilable_nodes(symbol_table)
    )


def lstrip_call(type_inference: intermediate_type_inference.TypeInference) -> bool:
    """
    Check whether any transpiled code calls ``str.lstrip``.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for ``lstrip``. We rely on the inferred
    types, so a method of our class named ``lstrip`` does not count.
    """
    return _calls_builtin_method(type_inference, intermediate_type_inference.STR_LSTRIP)


def rstrip_call(type_inference: intermediate_type_inference.TypeInference) -> bool:
    """
    Check whether any transpiled code calls ``str.rstrip``.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for ``rstrip``. We rely on the inferred
    types, so a method of our class named ``rstrip`` does not count.
    """
    return _calls_builtin_method(type_inference, intermediate_type_inference.STR_RSTRIP)


def startswith_call(
    type_inference: intermediate_type_inference.TypeInference,
) -> bool:
    """
    Check whether any transpiled code calls ``str.startswith``.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for ``startswith``.
    """
    return _calls_builtin_method(
        type_inference, intermediate_type_inference.STR_STARTSWITH
    )


def endswith_call(
    type_inference: intermediate_type_inference.TypeInference,
) -> bool:
    """
    Check whether any transpiled code calls ``str.endswith``.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for ``endswith``.
    """
    return _calls_builtin_method(
        type_inference, intermediate_type_inference.STR_ENDSWITH
    )


def string_operations(
    type_inference: intermediate_type_inference.TypeInference,
) -> bool:
    """
    Check whether any transpiled code might operate on strings.

    The operations are ``len``, slicing, ``find``, ordering, ``lstrip``,
    ``rstrip``, ``startswith`` and ``endswith``. The targets use this check to
    generate the unit tests of the operations on strings only if the meta-model
    needs them.
    """
    return (
        string_len_call(type_inference)
        or string_slicing(type_inference)
        or string_find_call(type_inference)
        or string_ordering(type_inference)
        or lstrip_call(type_inference)
        or rstrip_call(type_inference)
        or startswith_call(type_inference)
        or endswith_call(type_inference)
    )


def int_call(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether the meta-model calls the built-in ``int`` in transpilable code.

    The generators use this function to decide whether they need to generate
    the helper functions and the tests for parsing the integers.
    """
    return any(
        isinstance(node, parse_tree.FunctionCall) and node.name.identifier == "int"
        for node in _over_transpilable_nodes(symbol_table)
    )


def _nested_sets(
    type_annotation: _types.TypeAnnotationUnion,
) -> Iterator[_types.SetTypeAnnotation]:
    """Iterate over the sets in ``type_annotation`` at any depth."""
    for type_anno in _types.over_type_annotation_and_nested_type_annotations(
        type_annotation
    ):
        if isinstance(type_anno, _types.SetTypeAnnotation):
            yield type_anno


def sets_in(functions: Sequence[Union[_types.Verification, _types.Method]]) -> bool:
    """
    Check whether the ``functions`` take, return or declare local sets.

    The C++ generator uses this check to include ``<unordered_set>`` only where
    it is needed.
    """
    return any(
        any(
            any(True for _ in _nested_sets(argument.type_annotation))
            for argument in function.arguments
        )
        or (
            function.returns is not None
            and any(True for _ in _nested_sets(function.returns))
        )
        or _types.declares_local_set(function)
        for function in functions
    )


def sets(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether the meta-model might use the sets in transpilable code.

    The sets are the constant sets, the set arguments, the set return values and
    the local sets.
    The generators use this function to decide whether they need to generate
    the helper functions for the sets.
    """
    if any(
        isinstance(
            constant,
            (
                _types.ConstantSetOfPrimitives,
                _types.ConstantSetOfEnumerationLiterals,
            ),
        )
        for constant in symbol_table.constants
    ):
        return True

    functions: List[Union[_types.Verification, _types.Method]] = [
        *symbol_table.verification_functions,
        *(method for cls in symbol_table.classes for method in cls.methods),
    ]

    return sets_in(functions)


def set_operations(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether the meta-model computes an intersection or a difference of sets.

    The generators use this function to decide whether they need to generate
    the helper functions for the operations on sets.

    We do not distinguish between the methods of the sets and the methods of our
    classes of the same name. In the worst case, we generate unused helpers.
    """
    return any(
        isinstance(node, parse_tree.MethodCall)
        and node.member.name in ("intersection", "difference")
        for node in _over_transpilable_nodes(symbol_table)
    )


def set_properties(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether any class of the ``symbol_table`` has a property holding a set.

    The set can be at any depth of the property's type annotation, *e.g.*,
    ``List[Set[str]]``. The sets are serialized as sorted arrays, so we need to
    generate the helpers for sorting them only if there are any.
    """
    return any(
        any(True for _ in _nested_sets(prop.type_annotation))
        for cls in symbol_table.classes
        for prop in cls.properties
    )


def enumerations_in_set_properties(
    symbol_table: _types.SymbolTable,
) -> List[_types.Enumeration]:
    """
    List the enumerations whose literals are held in the sets of the properties.

    The sets can be at any depth of the properties' type annotations. The targets
    sort such a set by the ranks of its literals when they serialize it, so they
    need the helpers ranking the literals of these enumerations.

    The enumerations are listed in the order of their definition in
    the meta-model, each only once.
    """
    ids_in_sets: Set[int] = set()
    for cls in symbol_table.classes:
        for prop in cls.properties:
            for set_type_anno in _nested_sets(prop.type_annotation):
                if isinstance(
                    set_type_anno.items, _types.OurTypeAnnotation
                ) and isinstance(set_type_anno.items.our_type, _types.Enumeration):
                    ids_in_sets.add(id(set_type_anno.items.our_type))

    return [
        enumeration
        for enumeration in symbol_table.enumerations
        if id(enumeration) in ids_in_sets
    ]


def _items_of(
    type_annotation: _types.TypeAnnotationExceptOptional,
) -> Sequence[_types.TypeAnnotationUnion]:
    """Give the items of a list or of a tuple, and nothing for anything else."""
    if isinstance(type_annotation, _types.ListTypeAnnotation):
        return [type_annotation.items]

    if isinstance(type_annotation, _types.TupleTypeAnnotation):
        return type_annotation.items

    return []


def sets_nested_in_properties(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether any property holds a set nested in a list or in a tuple.

    The generators need this check to import the type of the set where they
    spell out the types of such lists and tuples, but not those of the sets
    themselves, *e.g.*, in the deep copies.
    """
    return any(
        any(True for _ in _nested_sets(item_type_anno))
        for cls in symbol_table.classes
        for prop in cls.properties
        for item_type_anno in _items_of(_types.beneath_optional(prop.type_annotation))
    )


def _holds_set_of_enumeration_literals(
    type_annotation: _types.TypeAnnotationUnion,
) -> bool:
    """Check whether ``type_annotation`` holds a set of enumeration literals at any depth."""
    return any(
        isinstance(set_type_anno.items, _types.OurTypeAnnotation)
        and isinstance(set_type_anno.items.our_type, _types.Enumeration)
        for set_type_anno in _nested_sets(type_annotation)
    )


def sets_of_enumeration_literals(symbol_table: _types.SymbolTable) -> bool:
    """
    Check whether the meta-model uses a set of enumeration literals.

    The sets are the constant sets, the set properties, the set arguments,
    the set return values and the local sets. We do not have the types of
    the local sets at hand here, so we resolve the items of ``Set[...]`` and
    ``AbstractSet[...]`` in the annotations of the local declarations.
    """
    if any(
        isinstance(constant, _types.ConstantSetOfEnumerationLiterals)
        for constant in symbol_table.constants
    ):
        return True

    if any(
        _holds_set_of_enumeration_literals(prop.type_annotation)
        for cls in symbol_table.classes
        for prop in cls.properties
    ):
        return True

    functions: List[Union[_types.Verification, _types.Method]] = [
        *symbol_table.verification_functions,
        *(method for cls in symbol_table.classes for method in cls.methods),
    ]

    for function in functions:
        if any(
            _holds_set_of_enumeration_literals(argument.type_annotation)
            for argument in function.arguments
        ):
            return True

        if function.returns is not None and _holds_set_of_enumeration_literals(
            function.returns
        ):
            return True

        for annotation in _types.local_declaration_annotations(function):
            for node in parse_tree.over_nodes(annotation):
                if (
                    isinstance(node, parse_tree.Index)
                    and isinstance(node.collection, parse_tree.Name)
                    and node.collection.identifier in ("Set", "AbstractSet")
                    and isinstance(node.index, parse_tree.Name)
                    and isinstance(
                        symbol_table.find_our_type(node.index.identifier),
                        _types.Enumeration,
                    )
                ):
                    return True

    return False


def sets_of_strings_in_properties(symbol_table: _types.SymbolTable) -> bool:
    """Check whether any class of the ``symbol_table`` has a property holding a set of strings."""
    return any(
        _types.try_primitive_type(set_type_anno.items) is _types.PrimitiveType.STR
        for cls in symbol_table.classes
        for prop in cls.properties
        for set_type_anno in _nested_sets(prop.type_annotation)
    )
