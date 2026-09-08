"""Stringify the intermediate representation."""

from typing import Union, Optional

from aas_core_codegen import stringify as stringify_mod
from aas_core_codegen.intermediate import _types, construction
from aas_core_codegen.intermediate._types import (
    AbstractClass,
    Argument,
    Class,
    ConcreteClass,
    ConstrainedPrimitive,
    Constructor,
    Contract,
    Contracts,
    Default,
    DefaultPrimitive,
    DefaultEnumerationLiteral,
    Enumeration,
    EnumerationLiteral,
    ImplementationSpecificMethod,
    ImplementationSpecificVerification,
    Interface,
    Invariant,
    ListTypeAnnotation,
    MetaModel,
    OptionalTypeAnnotation,
    OurTypeAnnotation,
    PatternVerification,
    PrimitiveTypeAnnotation,
    Property,
    Serialization,
    Signature,
    Snapshot,
    OurType,
    SymbolTable,
    TupleTypeAnnotation,
    UnderstoodMethod,
    DescriptionOfMetaModel,
    DescriptionOfOurType,
    DescriptionOfSignature,
    DescriptionOfProperty,
    DescriptionOfEnumerationLiteral,
    SignatureLike,
    ConstantPrimitive,
    ConstantSetOfPrimitives,
    ConstantSetOfEnumerationLiterals,
    PrimitiveSetLiteral,
    DescriptionOfConstant,
    TranspilableVerification,
)
from aas_core_codegen.parse import tree as parse_tree


def _stringify_primitive_type_annotation(
    that: PrimitiveTypeAnnotation,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("a_type", that.a_type.name),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_our_type_annotation(
    that: OurTypeAnnotation,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property(
                "our_type", f"Reference to our type {that.our_type.name}"
            ),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_list_type_annotation(
    that: ListTypeAnnotation,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("items", stringify(that.items)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_tuple_type_annotation(
    that: TupleTypeAnnotation,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("items", [stringify(item) for item in that.items]),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_optional_type_annotation(
    that: OptionalTypeAnnotation,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("value", stringify(that.value)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_description_of_meta_model(
    that: DescriptionOfMetaModel,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("summary", str(that.summary)),
            stringify_mod.Property("remarks", list(map(str, that.remarks))),
            stringify_mod.Property(
                "constraints_by_identifier",
                [
                    [identifier, str(body)]
                    for identifier, body in that.constraints_by_identifier.items()
                ],
            ),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_description_of_our_type(
    that: DescriptionOfOurType,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("summary", str(that.summary)),
            stringify_mod.Property("remarks", list(map(str, that.remarks))),
            stringify_mod.Property(
                "constraints_by_identifier",
                [
                    [identifier, str(body)]
                    for identifier, body in that.constraints_by_identifier.items()
                ],
            ),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_description_of_property(
    that: DescriptionOfProperty,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("summary", str(that.summary)),
            stringify_mod.Property("remarks", list(map(str, that.remarks))),
            stringify_mod.Property(
                "constraints_by_identifier",
                [
                    [identifier, str(body)]
                    for identifier, body in that.constraints_by_identifier.items()
                ],
            ),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_description_of_enumeration_literal(
    that: DescriptionOfEnumerationLiteral,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("summary", str(that.summary)),
            stringify_mod.Property("remarks", list(map(str, that.remarks))),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_description_of_signature(
    that: DescriptionOfSignature,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("summary", str(that.summary)),
            stringify_mod.Property("remarks", list(map(str, that.remarks))),
            stringify_mod.Property(
                "arguments_by_name",
                [[name, str(body)] for name, body in that.arguments_by_name.items()],
            ),
            stringify_mod.Property(
                "returns", None if that.returns is None else str(that.returns)
            ),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_description_of_constant(
    that: DescriptionOfConstant,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("summary", str(that.summary)),
            stringify_mod.Property("remarks", list(map(str, that.remarks))),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_property(
    that: Property,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("type_annotation", stringify(that.type_annotation)),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.Property(
                "specified_for",
                f"Reference to {that.specified_for.__class__.__name__} "
                f"{that.specified_for.name}",
            ),
            stringify_mod.Property("json_name", that.json_name),
            stringify_mod.Property("xml_name", that.xml_name),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_default_primitive(
    that: DefaultPrimitive,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("value", that.value),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_default_enumeration_literal(
    that: DefaultEnumerationLiteral,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property(
                "enumeration",
                f"Reference to {that.enumeration.__class__.__name__} "
                f"{that.enumeration.name}",
            ),
            stringify_mod.Property(
                "literal",
                f"Reference to {that.literal.__class__.__name__} "
                f"{that.literal.name}",
            ),
        ],
    )

    return result


def _stringify_argument(
    that: Argument,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("type_annotation", stringify(that.type_annotation)),
            stringify_mod.Property("default", stringify(that.default)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_serialization(
    that: Serialization,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("with_model_type", that.with_model_type),
        ],
    )

    return result


def _stringify_invariant(
    that: Invariant,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("description", that.description),
            stringify_mod.Property("body", parse_tree.dump(that.body)),
            stringify_mod.Property(
                "specified_for",
                f"Reference to {that.specified_for.__class__.__name__} "
                f"{that.specified_for.name}",
            ),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_contract(
    that: Contract,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("args", that.args),
            stringify_mod.Property("description", that.description),
            stringify_mod.Property("body", parse_tree.dump(that.body)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_snapshot(
    that: Snapshot,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("args", that.args),
            stringify_mod.Property("body", parse_tree.dump(that.body)),
            stringify_mod.Property("name", that.name),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_contracts(that: Contracts) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property(
                "preconditions", list(map(stringify, that.preconditions))
            ),
            stringify_mod.Property("snapshots", list(map(stringify, that.snapshots))),
            stringify_mod.Property(
                "postconditions",
                list(map(stringify, that.postconditions)),
            ),
        ],
    )

    return result


def _stringify_a_signature_like(that: SignatureLike) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("arguments", list(map(stringify, that.arguments))),
            stringify_mod.Property("returns", stringify(that.returns)),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.Property("contracts", stringify(that.contracts)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
            stringify_mod.PropertyEllipsis("arguments_by_name", that.arguments_by_name),
        ],
    )

    return result


def _stringify_implementation_specific_method(
    that: ImplementationSpecificMethod,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("arguments", list(map(stringify, that.arguments))),
            stringify_mod.Property("returns", stringify(that.returns)),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.Property(
                "specified_for",
                f"Reference to {that.specified_for.__class__.__name__} "
                f"{that.specified_for.name}",
            ),
            stringify_mod.Property("contracts", stringify(that.contracts)),
            stringify_mod.Property("non_mutating", that.non_mutating),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
            stringify_mod.PropertyEllipsis("arguments_by_name", that.arguments_by_name),
        ],
    )

    return result


def _stringify_understood_method(
    that: UnderstoodMethod,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("arguments", list(map(stringify, that.arguments))),
            stringify_mod.Property("returns", stringify(that.returns)),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.Property(
                "specified_for",
                f"Reference to {that.specified_for.__class__.__name__} "
                f"{that.specified_for.name}",
            ),
            stringify_mod.Property("contracts", stringify(that.contracts)),
            stringify_mod.Property("non_mutating", that.non_mutating),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
            stringify_mod.Property(
                "body", [parse_tree.dump(stmt) for stmt in that.body]
            ),
            stringify_mod.PropertyEllipsis("arguments_by_name", that.arguments_by_name),
        ],
    )

    return result


def _stringify_constructor(
    that: Constructor,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("arguments", list(map(stringify, that.arguments))),
            stringify_mod.Property("returns", stringify(that.returns)),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.Property("contracts", stringify(that.contracts)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
            stringify_mod.PropertyEllipsis("arguments_by_name", that.arguments_by_name),
            stringify_mod.Property(
                "is_implementation_specific", that.is_implementation_specific
            ),
            stringify_mod.Property(
                "statements", list(map(construction.dump, that.statements))
            ),
            stringify_mod.Property(
                "inlined_statements",
                list(map(construction.dump, that.inlined_statements)),
            ),
        ],
    )

    return result


def _stringify_enumeration_literal(
    that: EnumerationLiteral,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("value", that.value),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_enumeration(
    that: Enumeration,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("literals", list(map(stringify, that.literals))),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("literals_by_name", that.literals_by_name),
            stringify_mod.PropertyEllipsis("literals_by_value", that.literals_by_value),
            stringify_mod.PropertyEllipsis("literal_id_set", that.literal_id_set),
            stringify_mod.PropertyEllipsis("literal_value_set", that.literal_value_set),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_constrained_primitive(
    that: ConstrainedPrimitive,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property(
                "inheritances",
                [
                    f"Reference to {inheritance.__class__.__name__} {inheritance.name}"
                    for inheritance in that.inheritances
                ],
            ),
            stringify_mod.PropertyEllipsis(
                "inheritance_id_set", that.inheritance_id_set
            ),
            stringify_mod.Property(
                "ancestors",
                [
                    f"Reference to {ancestor.__class__.__name__} {ancestor.name}"
                    for ancestor in that.ancestors
                ],
            ),
            stringify_mod.PropertyEllipsis("ancestor_id_set", that.ancestor_id_set),
            stringify_mod.Property(
                "descendants",
                [
                    f"Reference to {descendant.__class__.__name__} {descendant.name}"
                    for descendant in that.descendants
                ],
            ),
            stringify_mod.PropertyEllipsis("descendant_id_set", that.descendant_id_set),
            stringify_mod.Property("constrainee", that.constrainee.name),
            stringify_mod.Property(
                "is_implementation_specific", that.is_implementation_specific
            ),
            stringify_mod.Property("invariants", list(map(stringify, that.invariants))),
            stringify_mod.PropertyEllipsis("invariant_id_set", that.invariant_id_set),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_a_class(that: Class) -> stringify_mod.Entity:
    # NOTE (mristin, 2021-12-26):
    # Concrete and abstract class share all the attributes, so we provide a single
    # stringification function.

    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property(
                "inheritances",
                [
                    f"Reference to {inheritance.__class__.__name__} {inheritance.name}"
                    for inheritance in that.inheritances
                ],
            ),
            stringify_mod.PropertyEllipsis(
                "inheritance_id_set", that.inheritance_id_set
            ),
            stringify_mod.Property(
                "ancestors",
                [
                    f"Reference to {ancestor.__class__.__name__} {ancestor.name}"
                    for ancestor in that.ancestors
                ],
            ),
            stringify_mod.PropertyEllipsis("ancestor_id_set", that.ancestor_id_set),
            stringify_mod.Property(
                "is_implementation_specific", that.is_implementation_specific
            ),
            stringify_mod.Property("interface", stringify(that.interface)),
            stringify_mod.PropertyEllipsis("descendant_id_set", that.descendant_id_set),
            stringify_mod.Property(
                "descendants",
                [
                    f"Reference to {descendant.__class__.__name__} {descendant.name}"
                    for descendant in that.descendants
                ],
            ),
            stringify_mod.PropertyEllipsis(
                "concrete_descendant_id_set", that.concrete_descendant_id_set
            ),
            stringify_mod.Property(
                "concrete_descendants",
                [
                    f"Reference to {descendant.__class__.__name__} {descendant.name}"
                    for descendant in that.concrete_descendants
                ],
            ),
            stringify_mod.Property("properties", list(map(stringify, that.properties))),
            stringify_mod.Property("methods", list(map(stringify, that.methods))),
            stringify_mod.Property("constructor", stringify(that.constructor)),
            stringify_mod.Property("invariants", list(map(stringify, that.invariants))),
            stringify_mod.Property("serialization", stringify(that.serialization)),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
            stringify_mod.PropertyEllipsis(
                "properties_by_name", that.properties_by_name
            ),
            stringify_mod.PropertyEllipsis("property_id_set", that.property_id_set),
            stringify_mod.PropertyEllipsis("methods_by_name", that.methods_by_name),
            stringify_mod.PropertyEllipsis("method_id_set", that.method_id_set),
            stringify_mod.PropertyEllipsis("invariant_id_set", that.invariant_id_set),
        ],
    )

    return result


def _stringify_concrete_class(that: ConcreteClass) -> stringify_mod.Entity:
    return _stringify_a_class(that)


def _stringify_abstract_class(that: AbstractClass) -> stringify_mod.Entity:
    return _stringify_a_class(that)


def _stringify_constant_primitive(
    that: ConstantPrimitive,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("value", that.value),
            stringify_mod.Property("a_type", that.a_type.name),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_primitive_set_literal(
    that: PrimitiveSetLiteral,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("value", that.value),
            stringify_mod.Property("a_type", that.a_type.name),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_constant_set_of_primitives(
    that: ConstantSetOfPrimitives,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property("a_type", that.a_type.name),
            stringify_mod.Property("literals", list(map(stringify, that.literals))),
            stringify_mod.PropertyEllipsis("literal_value_set", that.literal_value_set),
            stringify_mod.Property(
                "subsets",
                [
                    f"Reference to {subset.__class__.__name__} {subset.name}"
                    for subset in that.subsets
                ],
            ),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_constant_set_of_enumeration_literals(
    that: ConstantSetOfEnumerationLiterals,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("name", that.name),
            stringify_mod.Property(
                "enumeration",
                f"Reference to {that.enumeration.__class__.__name__} "
                f"{that.enumeration.name}",
            ),
            stringify_mod.Property(
                "literals",
                [
                    f"Reference to {literal.__class__.__name__} {literal.name}"
                    for literal in that.literals
                ],
            ),
            stringify_mod.PropertyEllipsis("literal_id_set", that.literal_id_set),
            stringify_mod.PropertyEllipsis("literal_value_set", that.literal_value_set),
            stringify_mod.Property(
                "subsets",
                [
                    f"Reference to {subset.__class__.__name__} {subset.name}"
                    for subset in that.subsets
                ],
            ),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
        ],
    )

    return result


def _stringify_implementation_specific_verification(
    that: ImplementationSpecificVerification,
) -> stringify_mod.Entity:
    return _stringify_a_signature_like(that)


def _stringify_pattern_verification(
    that: PatternVerification,
) -> stringify_mod.Entity:
    signature_like = _stringify_a_signature_like(that)

    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=list(signature_like.properties)
        + [stringify_mod.Property("pattern", that.pattern)]
        + [stringify_mod.Property("pattern_expr", parse_tree.dump(that.pattern_expr))],
    )

    return result


def _stringify_transpilable_verification(
    that: TranspilableVerification,
) -> stringify_mod.Entity:
    signature_like = _stringify_a_signature_like(that)

    result = stringify_mod.Entity(
        name=that.__class__.__name__, properties=list(signature_like.properties)
    )

    return result


def _stringify_signature(
    that: Signature,
) -> stringify_mod.Entity:
    return _stringify_a_signature_like(that)


def _stringify_interface(
    that: Interface,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property(
                "base",
                f"Reference to {that.base.__class__.__name__} {that.base.name}",
            ),
            stringify_mod.Property("name", that.name),
            stringify_mod.Property(
                "inheritances",
                [
                    f"Reference to {inheritance.__class__.__name__} {inheritance.name}"
                    for inheritance in that.inheritances
                ],
            ),
            stringify_mod.Property(
                "implementers",
                [
                    f"Reference to {implementer.__class__.__name__} {implementer.name}"
                    for implementer in that.implementers
                ],
            ),
            stringify_mod.Property("properties", list(map(stringify, that.properties))),
            stringify_mod.Property("signatures", list(map(stringify, that.signatures))),
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.PropertyEllipsis("parsed", that.parsed),
            stringify_mod.PropertyEllipsis(
                "properties_by_name", that.properties_by_name
            ),
            stringify_mod.PropertyEllipsis("property_id_set", that.property_id_set),
        ],
    )

    return result


def _stringify_meta_model(
    that: MetaModel,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("description", stringify(that.description)),
            stringify_mod.Property("version", that.version),
            stringify_mod.Property("xml_namespace", that.xml_namespace),
        ],
    )

    return result


def _stringify_symbol_table(
    that: SymbolTable,
) -> stringify_mod.Entity:
    result = stringify_mod.Entity(
        name=that.__class__.__name__,
        properties=[
            stringify_mod.Property("our_types", list(map(stringify, that.our_types))),
            stringify_mod.Property(
                "our_types_topologically_sorted",
                [
                    f"Reference to our type {our_type.name}"
                    for our_type in that.our_types_topologically_sorted
                ],
            ),
            stringify_mod.Property(
                "enumerations",
                [
                    f"Reference to our type {our_type.name}"
                    for our_type in that.enumerations
                ],
            ),
            stringify_mod.Property(
                "constrained_primitives",
                [
                    f"Reference to our type {our_type.name}"
                    for our_type in that.constrained_primitives
                ],
            ),
            stringify_mod.Property(
                "classes",
                [f"Reference to our type {our_type.name}" for our_type in that.classes],
            ),
            stringify_mod.Property(
                "concrete_classes",
                [
                    f"Reference to our type {our_type.name}"
                    for our_type in that.concrete_classes
                ],
            ),
            stringify_mod.Property("constants", list(map(stringify, that.constants))),
            stringify_mod.PropertyEllipsis("constants_by_name", that.constants_by_name),
            stringify_mod.Property(
                "verification_functions",
                list(map(stringify, that.verification_functions)),
            ),
            stringify_mod.PropertyEllipsis(
                "verification_functions_by_name", that.verification_functions_by_name
            ),
            stringify_mod.Property("meta_model", stringify(that.meta_model)),
        ],
    )

    return result


Dumpable = Union[
    AbstractClass,
    Argument,
    ConcreteClass,
    ConstantPrimitive,
    ConstantSetOfEnumerationLiterals,
    ConstantSetOfPrimitives,
    Constructor,
    Contract,
    Contracts,
    Default,
    DescriptionOfMetaModel,
    DescriptionOfOurType,
    DescriptionOfProperty,
    DescriptionOfEnumerationLiteral,
    DescriptionOfSignature,
    DescriptionOfConstant,
    Enumeration,
    EnumerationLiteral,
    ImplementationSpecificMethod,
    ImplementationSpecificVerification,
    Interface,
    Invariant,
    ListTypeAnnotation,
    MetaModel,
    OptionalTypeAnnotation,
    OurTypeAnnotation,
    PatternVerification,
    TranspilableVerification,
    PrimitiveSetLiteral,
    PrimitiveTypeAnnotation,
    Property,
    Serialization,
    Signature,
    Snapshot,
    OurType,
    SymbolTable,
    TupleTypeAnnotation,
    UnderstoodMethod,
]

stringify_mod.assert_all_public_types_listed_as_dumpables(
    dumpable=Dumpable, types_module=_types
)

_DISPATCH = {
    AbstractClass: _stringify_abstract_class,
    Argument: _stringify_argument,
    ConcreteClass: _stringify_concrete_class,
    ConstantPrimitive: _stringify_constant_primitive,
    ConstantSetOfEnumerationLiterals: _stringify_constant_set_of_enumeration_literals,
    ConstantSetOfPrimitives: _stringify_constant_set_of_primitives,
    ConstrainedPrimitive: _stringify_constrained_primitive,
    Constructor: _stringify_constructor,
    Contract: _stringify_contract,
    Contracts: _stringify_contracts,
    DefaultPrimitive: _stringify_default_primitive,
    DefaultEnumerationLiteral: _stringify_default_enumeration_literal,
    DescriptionOfConstant: _stringify_description_of_constant,
    DescriptionOfMetaModel: _stringify_description_of_meta_model,
    DescriptionOfOurType: _stringify_description_of_our_type,
    DescriptionOfProperty: _stringify_description_of_property,
    DescriptionOfEnumerationLiteral: _stringify_description_of_enumeration_literal,
    DescriptionOfSignature: _stringify_description_of_signature,
    Enumeration: _stringify_enumeration,
    EnumerationLiteral: _stringify_enumeration_literal,
    ImplementationSpecificMethod: _stringify_implementation_specific_method,
    ImplementationSpecificVerification: _stringify_implementation_specific_verification,
    Interface: _stringify_interface,
    Invariant: _stringify_invariant,
    ListTypeAnnotation: _stringify_list_type_annotation,
    MetaModel: _stringify_meta_model,
    OptionalTypeAnnotation: _stringify_optional_type_annotation,
    OurTypeAnnotation: _stringify_our_type_annotation,
    PatternVerification: _stringify_pattern_verification,
    PrimitiveSetLiteral: _stringify_primitive_set_literal,
    PrimitiveTypeAnnotation: _stringify_primitive_type_annotation,
    Property: _stringify_property,
    Serialization: _stringify_serialization,
    TupleTypeAnnotation: _stringify_tuple_type_annotation,
    Signature: _stringify_signature,
    Snapshot: _stringify_snapshot,
    SymbolTable: _stringify_symbol_table,
    TranspilableVerification: _stringify_transpilable_verification,
    UnderstoodMethod: _stringify_understood_method,
}

stringify_mod.assert_dispatch_exhaustive(dispatch=_DISPATCH, dumpable=Dumpable)


def stringify(that: Optional[Dumpable]) -> Optional[stringify_mod.Entity]:
    """Dispatch to the correct ``_stringify_*`` method."""
    if that is None:
        return None

    stringify_func = _DISPATCH.get(that.__class__, None)
    if stringify_func is None:
        raise AssertionError(
            f"No stringify function could be found for the class {that.__class__}"
        )

    stringified = stringify_func(that)  # type: ignore
    assert isinstance(stringified, stringify_mod.Entity)
    stringify_mod.assert_compares_against_dict(stringified, that)

    return stringified


def dump(that: Optional[Dumpable]) -> str:
    """Produce a string representation of the ``dumpable`` for testing or debugging."""
    if that is None:
        return repr(None)

    stringified = stringify(that)
    return stringify_mod.dump(stringified)
