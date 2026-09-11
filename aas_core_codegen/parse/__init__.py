"""Parse the meta model."""

from aas_core_codegen.parse import _types, _translate, _stringify

TypeAnnotation = _types.TypeAnnotation
AtomicTypeAnnotation = _types.AtomicTypeAnnotation
SelfTypeAnnotation = _types.SelfTypeAnnotation
SubscriptedTypeAnnotation = _types.SubscriptedTypeAnnotation
Description = _types.Description
ConstantPrimitive = _types.ConstantPrimitive
SetLiteral = _types.SetLiteral
ConstantSet = _types.ConstantSet
ConstantUnion = _types.ConstantUnion
Property = _types.Property
Default = _types.Default
Argument = _types.Argument
Invariant = _types.Invariant
Contract = _types.Contract
Snapshot = _types.Snapshot
Contracts = _types.Contracts
is_string_expr = _types.is_string_expr
ImplementationSpecificMethod = _types.ImplementationSpecificMethod
UnderstoodMethod = _types.UnderstoodMethod
ConstructorToBeUnderstood = _types.ConstructorToBeUnderstood
Method = _types.Method
MethodUnion = _types.MethodUnion
FunctionUnion = _types.FunctionUnion
OurType = _types.OurType
Serialization = _types.Serialization
Class = _types.Class
AbstractClass = _types.AbstractClass
ClassUnion = _types.ClassUnion
ConcreteClass = _types.ConcreteClass
EnumerationLiteral = _types.EnumerationLiteral
Enumeration = _types.Enumeration
NamedUnion = _types.NamedUnion
MetaModel = _types.MetaModel
SymbolTable = _types.SymbolTable

PRIMITIVE_TYPES = _types.PRIMITIVE_TYPES
GENERIC_TYPES = _types.GENERIC_TYPES
JSON_VALUE_TYPE_NAME = _types.JSON_VALUE_TYPE_NAME
JSON_ARRAY_TYPE_NAME = _types.JSON_ARRAY_TYPE_NAME

source_to_atok = _translate.source_to_atok
check_expected_imports = _translate.check_expected_imports
atok_to_symbol_table = _translate.atok_to_symbol_table

dump = _stringify.dump
