"""Provide the intermediate representation of the meta-model."""

from aas_core_codegen.intermediate import _types, _translate, _stringify

TypeAnnotation = _types.TypeAnnotation
TypeAnnotationUnion = _types.TypeAnnotationUnion
AtomicTypeAnnotation = _types.AtomicTypeAnnotation
AtomicTypeAnnotationAsTuple = _types.AtomicTypeAnnotationAsTuple
PrimitiveType = _types.PrimitiveType
PRIMITIVE_TYPE_TO_PYTHON_TYPE = _types.PRIMITIVE_TYPE_TO_PYTHON_TYPE
PYTHON_TYPE_TO_PRIMITIVE_TYPE = _types.PYTHON_TYPE_TO_PRIMITIVE_TYPE
PrimitiveTypeAnnotation = _types.PrimitiveTypeAnnotation
OurTypeAnnotation = _types.OurTypeAnnotation
ListTypeAnnotation = _types.ListTypeAnnotation
TupleTypeAnnotation = _types.TupleTypeAnnotation
OptionalTypeAnnotation = _types.OptionalTypeAnnotation
JsonValueTypeAnnotation = _types.JsonValueTypeAnnotation
JsonArrayTypeAnnotation = _types.JsonArrayTypeAnnotation
JsonObjectTypeAnnotation = _types.JsonObjectTypeAnnotation
SummaryRemarksDescription = _types.SummaryRemarksDescription
SummaryRemarksConstraintsDescription = _types.SummaryRemarksConstraintsDescription
DescriptionOfMetaModel = _types.DescriptionOfMetaModel
DescriptionOfOurType = _types.DescriptionOfOurType
DescriptionOfProperty = _types.DescriptionOfProperty
DescriptionOfEnumerationLiteral = _types.DescriptionOfEnumerationLiteral
DescriptionOfSignature = _types.DescriptionOfSignature
DescriptionOfConstant = _types.DescriptionOfConstant
DescriptionUnion = _types.DescriptionUnion
Property = _types.Property
Default = _types.Default
DefaultPrimitive = _types.DefaultPrimitive
DefaultEnumerationLiteral = _types.DefaultEnumerationLiteral
Argument = _types.Argument
OurType = _types.OurType
OurTypeExceptEnumeration = _types.OurTypeExceptEnumeration
Invariant = _types.Invariant
Contract = _types.Contract
Snapshot = _types.Snapshot
Contracts = _types.Contracts
Method = _types.Method
ImplementationSpecificMethod = _types.ImplementationSpecificMethod
UnderstoodMethod = _types.UnderstoodMethod
MethodUnion = _types.MethodUnion
Constructor = _types.Constructor
Serialization = _types.Serialization
EnumerationLiteral = _types.EnumerationLiteral
Enumeration = _types.Enumeration
ConstrainedPrimitive = _types.ConstrainedPrimitive
Class = _types.Class
ClassUnion = _types.ClassUnion
ConcreteClass = _types.ConcreteClass
AbstractClass = _types.AbstractClass
ConstantPrimitive = _types.ConstantPrimitive
PrimitiveSetLiteral = _types.PrimitiveSetLiteral
Constant = _types.Constant
ConstantSetOfPrimitives = _types.ConstantSetOfPrimitives
ConstantSetOfEnumerationLiterals = _types.ConstantSetOfEnumerationLiterals
ConstantSetUnion = _types.ConstantSetUnion
ConstantUnion = _types.ConstantUnion
Verification = _types.Verification
ImplementationSpecificVerification = _types.ImplementationSpecificVerification
PatternVerification = _types.PatternVerification
TranspilableVerification = _types.TranspilableVerification
VerificationUnion = _types.VerificationUnion
Signature = _types.Signature
Interface = _types.Interface
NamedUnion = _types.NamedUnion
SymbolTable = _types.SymbolTable

type_annotations_equal = _types.type_annotations_equal
beneath_optional = _types.beneath_optional
TypeAnnotationExceptOptional = _types.TypeAnnotationExceptOptional
try_primitive_type = _types.try_primitive_type
map_descendability = _types.map_descendability
collect_ids_of_our_types_in_properties = _types.collect_ids_of_our_types_in_properties
over_type_annotation_and_nested_type_annotations = (
    _types.over_type_annotation_and_nested_type_annotations
)
tuple_arities = _types.tuple_arities
model_uses_json_types = _types.model_uses_json_types

translate = _translate.translate
errors_if_contracts_for_functions_or_methods_defined = (
    _translate.errors_if_contracts_for_functions_or_methods_defined
)
errors_if_non_implementation_specific_methods = (
    _translate.errors_if_non_implementation_specific_methods
)

dump = _stringify.dump
stringify = _stringify.stringify
