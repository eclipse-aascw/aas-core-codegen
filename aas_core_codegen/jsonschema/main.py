"""Generate JSON schema corresponding to the meta-model."""
import collections
import itertools
import json
from typing import (
    TextIO,
    Any,
    MutableMapping,
    Optional,
    Tuple,
    List,
    Sequence,
    Mapping,
    Callable,
    Iterator,
    Final,
    cast,
)

from icontract import ensure, require

import aas_core_codegen.jsonschema
from aas_core_codegen import (
    naming,
    specific_implementations,
    intermediate,
    run,
    infer_for_schema,
)
from aas_core_codegen.parse import retree as parse_retree
from aas_core_codegen.common import (
    Stripped,
    Error,
    assert_never,
    Identifier,
    NonEmptyString,
)

assert aas_core_codegen.jsonschema.__doc__ == __doc__


def _define_for_enumeration(
    enumeration: intermediate.Enumeration,
) -> MutableMapping[str, Any]:
    """
    Generate the definition for an ``enumeration``.

    The list of definitions is to be *extended* with the resulting mapping.
    """
    definition = collections.OrderedDict()  # type: MutableMapping[str, Any]
    definition["type"] = "string"
    definition["enum"] = sorted(literal.value for literal in enumeration.literals)

    model_type = naming.json_model_type(enumeration.name)

    return collections.OrderedDict([(model_type, definition)])


_PRIMITIVE_MAP = {
    intermediate.PrimitiveType.BOOL: "boolean",
    intermediate.PrimitiveType.INT: "integer",
    intermediate.PrimitiveType.FLOAT: "number",
    intermediate.PrimitiveType.STR: "string",
    intermediate.PrimitiveType.BYTEARRAY: "string",
}
assert all(literal in _PRIMITIVE_MAP for literal in intermediate.PrimitiveType)


class _AllOf:
    """Represent a sequence of JSON schema declarations."""

    subschemas: Final[Sequence[Mapping[str, Any]]]

    @require(lambda subschemas: len(subschemas) > 0)
    def __init__(self, subschemas: Sequence[Mapping[str, Any]]) -> None:
        self.subschemas = subschemas


def _translate_constraints(
    type_annotation: intermediate.TypeAnnotationExceptOptional,
    constraints: Optional[infer_for_schema.Constraints],
    fix_pattern: Callable[[str], str],
) -> Optional[_AllOf]:
    """
    Translate the constraints for a value into JSON schema.

    If none of the constraints could be translated, return None.
    """
    if constraints is None:
        return None

    primitive_type = intermediate.try_primitive_type(type_annotation)

    base_subschema: MutableMapping[str, Any] = collections.OrderedDict()

    additional_subschemas: List[MutableMapping[str, Any]] = []

    if primitive_type is not None:
        if (
            primitive_type
            in (intermediate.PrimitiveType.STR, intermediate.PrimitiveType.BYTEARRAY)
            and constraints.len_constraint is not None
        ):
            if constraints.len_constraint.min_value is not None:
                base_subschema["minLength"] = constraints.len_constraint.min_value

            if constraints.len_constraint.max_value is not None:
                base_subschema["maxLength"] = constraints.len_constraint.max_value

        if (
            primitive_type == intermediate.PrimitiveType.STR
            and constraints.patterns is not None
            and len(constraints.patterns) > 0
        ):
            if len(constraints.patterns) == 1:
                base_subschema["pattern"] = fix_pattern(constraints.patterns[0].pattern)
            else:
                iterator = iter(constraints.patterns)

                first_pattern = next(iterator)

                base_subschema["pattern"] = fix_pattern(first_pattern.pattern)

                for pattern_constraint in iterator:
                    additional_subschema: MutableMapping[
                        str, Any
                    ] = collections.OrderedDict()

                    additional_subschema["pattern"] = fix_pattern(
                        pattern_constraint.pattern
                    )

                    additional_subschemas.append(additional_subschema)

    if isinstance(type_annotation, intermediate.ListTypeAnnotation):
        if constraints.len_constraint is not None:
            if constraints.len_constraint.min_value is not None:
                base_subschema["minItems"] = constraints.len_constraint.min_value

            if constraints.len_constraint.max_value is not None:
                base_subschema["maxItems"] = constraints.len_constraint.max_value

    assert (
        not (len(base_subschema) == 0) or len(additional_subschemas) == 0
    ), "If base subschema is empty, no additional subschemas are expected."

    if len(base_subschema) == 0:
        return None

    return _AllOf([base_subschema] + additional_subschemas)


def _all_of_as_jsonable_mapping(all_of: _AllOf) -> MutableMapping[str, Any]:
    """
    Render the instance of AllOf JSON schema construct to a JSON-able mapping.

    If it consists of just one subschema, that schema is simply returned.
    """
    if len(all_of.subschemas) == 1:
        return cast(MutableMapping[str, Any], all_of.subschemas[0])

    # NOTE (mristin):
    # We want to make it easier for code generators to see the base schema *before*
    # ``allOf``, so that they can ignore ``allOf`` in case that they can not process
    # it, but still get enough relevant information from the first base subschema.
    mapping: MutableMapping[str, Any] = collections.OrderedDict(all_of.subschemas[0])

    mapping["allOf"] = all_of.subschemas[1:]

    return mapping


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _define_type(
    type_annotation: intermediate.TypeAnnotationExceptOptional,
    constraints_by_value: infer_for_schema.ConstraintsByValue,
    fix_pattern: Callable[[str], str],
) -> Tuple[Optional[MutableMapping[str, Any]], Optional[Error]]:
    """
    Generate the type definition for ``type_annotation``.

    The constraints-by-value define all the constraints of the class nesting a property
    of this type.

    The ``fix_pattern`` determines how the pattern should be translated for
    the regex engine. For example, some JSON schema verification engines expect only
    characters below Basic Multilingual Plane (BMP), and use surrogate pairs to
    represent characters above BMP.
    """
    definition: MutableMapping[str, Any] = collections.OrderedDict()

    constraints = constraints_by_value.get(type_annotation, None)

    primitive_type = intermediate.try_primitive_type(type_annotation)

    if primitive_type is not None:
        definition["type"] = _PRIMITIVE_MAP[primitive_type]

        if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            definition["contentEncoding"] = "base64"

    else:
        if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError(
                f"Expected to handle this path before with try_primitive_type: "
                f"{type_annotation=}, {primitive_type}"
            )

        elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
            model_type = naming.json_model_type(type_annotation.our_type.name)

            if isinstance(type_annotation.our_type, intermediate.Enumeration):
                return (
                    collections.OrderedDict([("$ref", f"#/definitions/{model_type}")]),
                    None,
                )

            elif isinstance(
                type_annotation.our_type, intermediate.ConstrainedPrimitive
            ):
                raise AssertionError(
                    "Expected to handle this path before with try_primitive_type"
                )

            elif isinstance(type_annotation.our_type, intermediate.Class):
                if len(type_annotation.our_type.concrete_descendants) > 0:
                    return (
                        collections.OrderedDict(
                            [("$ref", f"#/definitions/{model_type}_choice")]
                        ),
                        None,
                    )
                else:
                    return (
                        collections.OrderedDict(
                            [("$ref", f"#/definitions/{model_type}")]
                        ),
                        None,
                    )

            else:
                assert_never(type_annotation.our_type)

        elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
            assert not isinstance(
                type_annotation.items, intermediate.OptionalTypeAnnotation
            ), (
                "NOTE (mristin): Lists of optional values were not expected "
                "at the time when we implemented this. Please contact the developers "
                "if you need this functionality."
            )

            items_type_definition, items_error = _define_type(
                type_annotation=type_annotation.items,
                constraints_by_value=constraints_by_value,
                fix_pattern=fix_pattern,
            )

            if items_error is not None:
                return None, items_error

            assert items_type_definition is not None

            definition["type"] = "array"
            definition["items"] = items_type_definition

        elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
            items_type_definitions = []  # type: List[MutableMapping[str, Any]]
            for item_type_annotation in type_annotation.items:
                assert isinstance(
                    item_type_annotation, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    "NOTE (mristin): We only support tuples of atomic types "
                    "(primitives, constrained primitives, classes and enumerations); "
                    "this should have been caught before by "
                    "intermediate._translate._verify_only_simple_type_patterns."
                )

                item_type_definition, item_error = _define_type(
                    type_annotation=item_type_annotation,
                    constraints_by_value=constraints_by_value,
                    fix_pattern=fix_pattern,
                )

                if item_error is not None:
                    return None, item_error

                assert item_type_definition is not None
                items_type_definitions.append(item_type_definition)

            definition["type"] = "array"
            definition["items"] = items_type_definitions
            definition["minItems"] = len(items_type_definitions)
            definition["maxItems"] = len(items_type_definitions)
            definition["additionalItems"] = False

        else:
            assert_never(type_annotation)

    if constraints is None:
        return definition, None
    else:
        all_of = _translate_constraints(
            type_annotation=type_annotation,
            constraints=constraints,
            fix_pattern=fix_pattern,
        )

        if all_of is None:
            return definition, None

        base_subschema = all_of.subschemas[0]

        # NOTE (mristin):
        # We put the type definitions first for readability.
        definition.update(base_subschema)

        return (
            _all_of_as_jsonable_mapping(
                _AllOf([definition, *itertools.islice(all_of.subschemas, 1, None)])
            ),
            None,
        )


# NOTE (mristin):
# This function is made public so that we can use it in other schema generators such
# as the SHACL generator.
def fix_pattern_for_utf16(pattern: str) -> str:
    """Parse the pattern and re-render it for UTF-16-only regex engines."""
    regex, error = parse_retree.parse([pattern])
    if error is not None:
        raise ValueError(
            f"The pattern could not be parsed: {pattern!r}; error was: {error}"
        )

    assert regex is not None
    parse_retree.fix_for_utf16_regex_in_place(regex)

    parts = parse_retree.render(regex=regex)
    assert all(
        isinstance(part, str) for part in parts
    ), "Only string parts expected, no formatted values"

    # NOTE (mristin, 2023-03-15):
    # We have to make this transformation for mypy.
    parts_str = []  # type: List[str]
    for part in parts:
        assert isinstance(part, str), "Only string parts expected, no formatted values"
        parts_str.append(part)

    return "".join(parts_str)


def _over_non_optional_type_annotations(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> Iterator[intermediate.TypeAnnotationUnion]:
    """
    Iterate recursively over the type annotation and all its nested type annotations.

    The optional type annotations are recursed into, but will not be yielded.
    """
    if not isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        yield type_annotation

    if isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        yield from _over_non_optional_type_annotations(type_annotation.value)

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        yield from _over_non_optional_type_annotations(type_annotation.items)

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        for item in type_annotation.items:
            yield from _over_non_optional_type_annotations(item)

    elif isinstance(
        type_annotation,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        pass

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _define_properties(
    cls: intermediate.ClassUnion,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
    fix_pattern: Callable[[str], str],
) -> Tuple[Optional[MutableMapping[str, Any]], Optional[List[Error]]]:
    """
    Generate the definitions of the meta-model properties for the given ``cls``.

    The property ``modelType`` is defined separately as we need to distinguish
    cases where it is set (concrete class) and not (abstract class, or stub of
    a concrete class with descendants).

    The ``fix_pattern`` determines how the pattern should be translated for
    the regex engine. For example, some JSON schema verification engines expect only
    characters below Basic Multilingual Plane (BMP), and use surrogate pairs to
    represent characters above BMP.
    """
    errors = []  # type: List[Error]

    properties = collections.OrderedDict()  # type: MutableMapping[str, Any]

    constraints_by_value = constraints_by_class[cls]

    for prop in cls.properties:
        prop_name = prop.json_name

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        definition: Optional[MutableMapping[str, Any]] = None

        if prop.specified_for is cls:
            maybe_definition, error = _define_type(
                type_annotation=type_anno,
                constraints_by_value=constraints_by_value,
                fix_pattern=fix_pattern,
            )

            if error is not None:
                errors.append(error)
            else:
                assert maybe_definition is not None
                definition = maybe_definition
        else:
            # NOTE (mristin):
            # The properties are inherited through ``allOf``. We can not change the type
            # of property in the children as this would result in a conflict and
            # unsatisfiable schema. Therefore, we define the type for a property only
            # at the parent class, where the property is defined for the first time.
            #
            # However, children classes can tighten constraints, so we have to reflect
            # that here. While we could theoretically check for all the constraints
            # deep into the nested type annotations, we currently limit ourselves to
            # check only if the constraints differ at the property level due to
            # the lack of time.

            constraints = constraints_by_value.get(type_anno, None)
            if constraints is None:
                continue

            for parent in cls.inheritances:
                parent_constraints = constraints_by_class[parent].get(type_anno, None)

                # NOTE (mristin):
                # We leverage here the fact that we do not make additional copies
                # when merging the constraints in case where one of the constraints is
                # none (see ``infer_for_schema._inline._merge_*`` functions).
                if parent_constraints is not None:
                    assert (
                        constraints is not None
                    ), "We can only tighten the constraints, but not relax them."

                    # fmt: off
                    constraints = (
                        infer_for_schema
                        .tightening_steps_from_other_to_that_constraints(
                            that=constraints,
                            other=parent_constraints,
                        )
                    )
                    # fmt: on

            all_of = _translate_constraints(
                type_annotation=type_anno,
                constraints=constraints,
                fix_pattern=fix_pattern,
            )

            if all_of is not None:
                definition = _all_of_as_jsonable_mapping(all_of)

        # NOTE (mristin):
        # We do not want to pollute the schema with empty definitions.
        if definition is not None and len(definition) > 0:
            properties[prop_name] = definition

    if len(errors) > 0:
        return None, errors

    return properties, None


def _list_required_properties(cls: intermediate.ClassUnion) -> List[NonEmptyString]:
    """
    List all the properties which are required.

    Only the meta-model properties are listed, so this list might not be exhaustive.
    For example, the JSON property ``modelType`` is not listed here.
    """
    required = []  # type: List[NonEmptyString]
    for prop in cls.properties:
        # NOTE (mristin, 2023-02-06):
        # We stack the inheritance as ``allOf``. This will impose the stacking
        # of the required fields as well, so whenever you add a field to
        # a child ``required`` constraint, it will *extend* the list of
        # the required fields, *not* replace it.
        if prop.specified_for is not cls:
            continue

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            required.append(prop.json_name)

    return required


def _define_all_of_for_inheritance(
    cls: intermediate.ClassUnion,
) -> List[MutableMapping[str, Any]]:
    """Generate ``allOf`` definition as inheritance."""
    all_of = []  # type: List[MutableMapping[str, Any]]

    for inheritance in cls.inheritances:
        if isinstance(inheritance, intermediate.AbstractClass):
            all_of.append(
                {"$ref": f"#/definitions/{naming.json_model_type(inheritance.name)}"}
            )
        elif isinstance(inheritance, intermediate.ConcreteClass):
            # NOTE (mristin, 2023-03-13):
            # We distinguish between two definitions corresponding to the same concrete
            # class:
            #
            # 1) One definition defines only the class in abstract, so that
            #    it can be inherited. The abstract definition lacks the ``modelType``
            #    constant, as that would conflict in inheritance.
            # 2) The other definition corresponds to the concrete definition of
            #    the class that an instance has to fulfill. This definition includes
            #    the constant ``modelType``.
            #
            # We had to separate these two definitions to avoid conflicts in
            # ``modelType`` constant between a parent concrete class and a child
            # concrete class.
            all_of.append(
                {
                    "$ref": f"#/definitions/"
                    f"{naming.json_model_type(inheritance.name)}_abstract"
                }
            )

    return all_of


@require(lambda cls: len(cls.concrete_descendants) > 0)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_inheritable_definition(
    cls: intermediate.ClassUnion,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
    fix_pattern: Callable[[str], str],
) -> Tuple[Optional[MutableMapping[str, Any]], Optional[List[Error]]]:
    """
    Generate a definition of ``cls`` for inheritance through ``allOf``.

    The ``fix_pattern`` determines how the pattern should be translated for
    the respective JSON schema engine.

    The definitions are to be *extended* with the resulting mapping.
    """
    all_of = _define_all_of_for_inheritance(cls)

    errors = []  # type: List[Error]

    properties, properties_error = _define_properties(
        cls=cls,
        constraints_by_class=constraints_by_class,
        fix_pattern=fix_pattern,
    )
    if properties_error is not None:
        errors.extend(properties_error)

    if len(errors) > 0:
        return None, errors

    assert properties is not None

    required = _list_required_properties(cls)

    if cls.serialization.with_model_type and not any(
        inheritance.serialization.with_model_type for inheritance in cls.inheritances
    ):
        # NOTE (mristin, 2023-03-13):
        # This is going to be an abstract definition for inheritance, so we can not pin
        # the ``modelType`` to a fixed, constant value.
        assert "modelType" not in properties
        properties["modelType"] = {"$ref": "#/definitions/ModelType"}

        required.append(NonEmptyString("modelType"))

    definition = collections.OrderedDict()  # type: MutableMapping[str, Any]
    if len(cls.inheritances) == 0:
        definition["type"] = "object"

    if len(properties) > 0:
        definition["properties"] = properties

        if len(required) > 0:
            definition["required"] = required

    if len(definition) > 0:
        all_of.append(definition)

    definition_name: str
    if isinstance(cls, intermediate.AbstractClass):
        definition_name = naming.json_model_type(cls.name)
    elif isinstance(cls, intermediate.ConcreteClass):
        definition_name = f"{naming.json_model_type(cls.name)}_abstract"
    else:
        assert_never(cls)

    result = collections.OrderedDict()  # type: MutableMapping[str, Any]

    if len(all_of) == 0:
        result[definition_name] = {"type": "object"}
    elif len(all_of) == 1:
        result[definition_name] = all_of[0]
    else:
        result[definition_name] = {"allOf": all_of}

    return result, None


@require(lambda cls: len(cls.concrete_descendants) > 0)
def _generate_choice_definition(
    cls: intermediate.ClassUnion,
) -> MutableMapping[str, Any]:
    """
    Generate the definition of dispatching through ``oneOf``.

    The definitions are to be *extended* with the resulting mapping.
    """
    one_of = []  # type: List[Mapping[str, Any]]
    if isinstance(cls, intermediate.ConcreteClass):
        one_of.append({"$ref": f"#/definitions/{naming.json_model_type(cls.name)}"})

    for descendant in cls.concrete_descendants:
        one_of.append(
            {"$ref": f"#/definitions/{naming.json_model_type(descendant.name)}"}
        )

    return {f"{naming.json_model_type(cls.name)}_choice": {"oneOf": one_of}}


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_concrete_definition(
    cls: intermediate.ClassUnion,
    constraints_by_class: Mapping[
        intermediate.ClassUnion, infer_for_schema.ConstraintsByValue
    ],
    fix_pattern: Callable[[str], str],
) -> Tuple[Optional[MutableMapping[str, Any]], Optional[List[Error]]]:
    """
    Generate the definition of a concrete class to be matched by an instance.

    The ``fix_pattern`` determines how the pattern should be translated for
    the respective JSON schema engine.
    """
    # NOTE (mristin):
    # We distinguish between two definitions corresponding to the same concrete
    # class:
    #
    # 1) One definition defines only the class in abstract, so that
    #    it can be inherited. The abstract definition lacks the ``modelType``
    #    constant, as that would conflict in inheritance.
    # 2) The other definition corresponds to the concrete definition of
    #    the class that an instance has to fulfill. This definition includes
    #    the constant ``modelType``.
    #
    # We had to separate these two definitions to avoid conflicts in
    # ``modelType`` constant between a parent concrete class and a child
    # concrete class.

    model_type = naming.json_model_type(cls.name)

    if len(cls.concrete_descendants) > 0:
        assert cls.serialization.with_model_type, (
            f"Expected model type to be included in a class with concrete descendants "
            f"{cls.name!r}"
        )

        all_of = [
            {"$ref": f"#/definitions/{model_type}_abstract"},
            {"properties": {"modelType": {"const": model_type}}},
        ]  # type: List[MutableMapping[str, Any]]

        return {model_type: {"allOf": all_of}}, None

    all_of = _define_all_of_for_inheritance(cls)

    errors = []  # type: List[Error]

    properties, properties_error = _define_properties(
        cls=cls,
        constraints_by_class=constraints_by_class,
        fix_pattern=fix_pattern,
    )
    if properties_error is not None:
        errors.extend(properties_error)

    if len(errors) > 0:
        return None, errors

    assert properties is not None

    required = _list_required_properties(cls)

    if cls.serialization.with_model_type:
        properties["modelType"] = {"const": model_type}

    definition = collections.OrderedDict()  # type: MutableMapping[str, Any]
    if len(cls.inheritances) == 0:
        definition["type"] = "object"

    if len(properties) > 0:
        definition["properties"] = properties

        if len(required) > 0:
            definition["required"] = required

    all_of.append(definition)

    model_type = naming.json_model_type(cls.name)

    result = collections.OrderedDict()  # type: MutableMapping[str, Any]

    if len(all_of) == 0:
        result[model_type] = {"type": "object"}
    elif len(all_of) == 1:
        result[model_type] = all_of[0]
    else:
        result[model_type] = {"allOf": all_of}

    return result, None


class Definitions:
    """Store definitions of the schema as we go."""

    def __init__(self) -> None:
        """Initialize as empty."""
        self._definitions = collections.OrderedDict()  # type: MutableMapping[str, Any]

    def get(self) -> Mapping[str, Any]:
        """Get the content."""
        return self._definitions

    def update_for(
        self, our_type: intermediate.OurType, extension: Mapping[str, Any]
    ) -> Optional[Error]:
        """Update the definitions with ``extension`` related to ``our_type``."""
        for key, definition in extension.items():
            if key in self._definitions:
                return Error(
                    our_type.parsed.node,
                    f"One of the JSON definitions, {key}, "
                    f"for our type {our_type.name} has been "
                    f"already provided in the definitions; "
                    f"did you already perhaps define it in another "
                    f"implementation-specific snippet?",
                )

            self._definitions[key] = definition

        return None

    def update(self, extension: Mapping[str, Any]) -> Optional[Error]:
        """Update the definitions with ``extension`` unrelated to any of our types."""
        for key, definition in extension.items():
            if key in self._definitions:
                return Error(
                    None,
                    f"One of the JSON definitions, {key}, "
                    f"has been already provided in the definitions; "
                    f"did you already perhaps define it in another "
                    f"implementation-specific snippet?",
                )

            self._definitions[key] = definition

        return None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    fix_pattern: Callable[[str], str],
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """
    Generate the JSON schema based on the symbol table.

    The ``fix_pattern`` determines how the pattern should be translated for
    the respective JSON schema engine.

    This function is intended to be used not only by aas-core-codegen, but also for
    downstream clients. For example, the downstream clients should use this function
    to customize how patterns should be rendered / fixed for the respective regex
    engine.
    """
    schema_base_key = specific_implementations.ImplementationKey("schema_base.json")

    schema_base_json = spec_impls.get(schema_base_key, None)
    if schema_base_json is None:
        return None, [
            Error(
                None,
                f"The implementation snippet for the base schema "
                f"is missing: {schema_base_key}",
            )
        ]

    schema: MutableMapping[str, Any]

    try:
        # noinspection PyTypeChecker
        schema = json.loads(schema_base_json, object_pairs_hook=collections.OrderedDict)
    except json.JSONDecodeError as err:
        return None, [
            Error(
                None, f"Failed to parse the base schema from {schema_base_key}: {err}"
            )
        ]

    if "$id" in schema:
        return None, [
            Error(
                None,
                f"Unexpected property '$id' in the base JSON schema "
                f"from: {schema_base_key}",
            )
        ]

    # NOTE (mristin, 2022-08-25):
    # We use the same namespace in all the schemas for the consistency.
    schema["$id"] = symbol_table.meta_model.xml_namespace

    if "definitions" in schema:
        return None, [
            Error(
                None,
                f"The property ``definitions`` unexpected in the base JSON schema "
                f"from: {schema_base_key}",
            )
        ]

    errors = []  # type: List[Error]

    definitions = Definitions()

    constraints_by_class, some_errors = infer_for_schema.infer_constraints_by_class(
        symbol_table=symbol_table
    )

    if some_errors is not None:
        errors.extend(some_errors)

    if len(errors) > 0:
        return None, errors

    assert constraints_by_class is not None

    ids_of_our_types_in_properties = (
        intermediate.collect_ids_of_our_types_in_properties(symbol_table=symbol_table)
    )

    for our_type in symbol_table.our_types:
        if (
            isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            )
            and our_type.is_implementation_specific
        ):
            implementation_key = specific_implementations.ImplementationKey(
                f"{our_type.name}.json"
            )

            code = spec_impls.get(implementation_key, None)
            if code is None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The implementation is missing "
                        f"for the implementation-specific class: {implementation_key}",
                    )
                )
                continue

            try:
                # noinspection PyTypeChecker
                extension = json.loads(code, object_pairs_hook=collections.OrderedDict)
            except Exception as err:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"Failed to parse the JSON out of "
                        f"the specific implementation {implementation_key}: {err}",
                    )
                )
                continue

            if not isinstance(extension, dict):
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"Expected the implementation-specific snippet "
                        f"at {implementation_key} to be a JSON object, "
                        f"but got: {type(extension)}",
                    )
                )
                continue

            update_error = definitions.update_for(
                our_type=our_type, extension=extension
            )
            if update_error is not None:
                errors.append(update_error)

        else:
            if isinstance(our_type, intermediate.Enumeration):
                update_error = definitions.update_for(
                    our_type=our_type,
                    extension=_define_for_enumeration(enumeration=our_type),
                )
                if update_error is not None:
                    errors.append(update_error)

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                # NOTE (mristin):
                # We in-line the constraints from the constrained primitives directly
                # in the properties. We do not want to introduce separate definitions
                # for them as that would make it more difficult for downstream code
                # generators to generate meaningful code (*e.g.*, code generators for
                # OpenAPI3).
                continue

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                if len(our_type.concrete_descendants) > 0:
                    # region Inheritable
                    inheritable, definition_errors = _generate_inheritable_definition(
                        cls=our_type,
                        constraints_by_class=constraints_by_class,
                        fix_pattern=fix_pattern,
                    )

                    if definition_errors is not None:
                        errors.extend(definition_errors)
                        continue

                    assert inheritable is not None
                    update_error = definitions.update_for(
                        our_type=our_type, extension=inheritable
                    )
                    if update_error is not None:
                        errors.append(update_error)
                    # endregion

                    # region Choice
                    if isinstance(our_type, intermediate.ConcreteClass) or (
                        isinstance(our_type, intermediate.AbstractClass)
                        and id(our_type) in ids_of_our_types_in_properties
                    ):
                        update_error = definitions.update_for(
                            our_type=our_type,
                            extension=_generate_choice_definition(cls=our_type),
                        )
                        if update_error is not None:
                            errors.append(update_error)
                    # endregion

                if isinstance(our_type, intermediate.ConcreteClass):
                    definition, definition_errors = _generate_concrete_definition(
                        cls=our_type,
                        constraints_by_class=constraints_by_class,
                        fix_pattern=fix_pattern,
                    )
                    if definition_errors is not None:
                        errors.extend(definition_errors)
                        continue

                    assert definition is not None

                    update_error = definitions.update_for(
                        our_type=our_type, extension=definition
                    )
                    if update_error is not None:
                        errors.append(update_error)
                else:
                    assert isinstance(our_type, intermediate.AbstractClass)

                    # We do not generate any concrete definition for an abstract class.
                    pass
            else:
                assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    model_types = sorted(
        naming.json_model_type(cls.name)
        for cls in symbol_table.concrete_classes
        if cls.serialization.with_model_type
    )  # type: List[Identifier]

    definitions.update(
        {
            "ModelType": collections.OrderedDict(
                [("type", "string"), ("enum", model_types)]
            )
        }
    )

    definitions_mapping = definitions.get()

    schema["definitions"] = collections.OrderedDict(
        [
            (name, definitions_mapping[name])
            for name in sorted(definitions_mapping.keys())
        ]
    )

    return Stripped(json.dumps(schema, indent=2)), None


def execute(context: run.Context, stdout: TextIO, stderr: TextIO) -> int:
    """Generate the code."""
    code, errors = generate(
        symbol_table=context.symbol_table,
        spec_impls=context.spec_impls,
        fix_pattern=fix_pattern_for_utf16,
    )

    if errors is not None:
        run.write_error_report(
            message=f"Failed to generate the JSON Schema "
            f"based on {context.model_path}",
            errors=[context.lineno_columner.error_message(error) for error in errors],
            stderr=stderr,
        )
        return 1

    assert code is not None

    pth = context.output_dir / "schema.json"
    try:
        pth.write_text(code, encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to write the JSON schema to {pth}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")
    return 0
