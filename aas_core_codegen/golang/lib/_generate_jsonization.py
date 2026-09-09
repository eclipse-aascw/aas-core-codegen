"""Generate code for JSON de/serialization."""

import io
from typing import Tuple, Optional, List, Union

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
    assert_union_without_excluded,
)
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    description as golang_description,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


# region De-serialization


def _generate_bool_from_jsonable() -> Stripped:
    """Generate the function to decode a ``bool`` from a JSON-able."""
    return Stripped(
        f"""\
// Parse `jsonable` as a boolean, or return an error.
func boolFromJsonable(
{I}jsonable interface{{}},
) (result bool, err error) {{
{I}if jsonable == nil {{
{II}err = newDeserializationError(
{III}"Expected a boolean, but got null",
{II})
{II}return
{I}}}

{I}var ok bool
{I}result, ok = jsonable.(bool)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf("Expected a boolean, but got %T", jsonable),
{II})

{II}return
{I}}}

{I}return
}}"""
    )


def _generate_int64_from_jsonable() -> Stripped:
    """Generate the function to decode an ``int64`` from a JSON-able."""
    return Stripped(
        f"""\
// Parse `jsonable` as a 64-bit integer, or return an error.
func int64FromJsonable(
{I}jsonable interface{{}},
) (result int64, err error) {{
{I}if jsonable == nil {{
{II}err = newDeserializationError(
{III}"Expected an integer number, but got null",
{II})
{II}return
{I}}}

{I}f, ok := jsonable.(float64)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an integer number, but got %T",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

{I}if math.IsNaN(f) {{
{II}err = newDeserializationError(
{III}"Expected an integer number, but got a NaN",
{II})
{II}return
{I}}}

{I}if math.IsInf(f, 0) {{
{II}err = newDeserializationError(
{III}"Expected an integer number, but got an infinity",
{II})
{II}return
{I}}}

{I}if f != math.Trunc(f) {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an integer number, but got a non-integer: %v",
{IIII}f,
{III}),
{II})
{II}return
{I}}}

{I}result = int64(f)
{I}if f != float64(result) {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an integer number fitting into int64, but got: %v",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_float64_from_jsonable() -> Stripped:
    """Generate the function to decode a ``float`` from a JSON-able."""
    return Stripped(
        f"""\
// Parse `jsonable` as a 64-bit float, or return an error.
func float64FromJsonable(
{I}jsonable interface{{}},
) (result float64, err error) {{
{I}if jsonable == nil {{
{II}err = newDeserializationError(
{III}"Expected a number, but got null",
{II})
{II}return
{I}}}

{I}var ok bool
{I}result, ok = jsonable.(float64)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a number, but got %T",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_string_from_jsonable() -> Stripped:
    """Generate the function to decode a ``string`` from a JSON-able."""
    return Stripped(
        f"""\
// Parse `jsonable` as a string, or return an error.
func stringFromJsonable(
{I}jsonable interface{{}},
) (result string, err error) {{
{I}if jsonable == nil {{
{II}err = newDeserializationError(
{III}"Expected a string, but got null",
{II})
{II}return
{I}}}

{I}var ok bool
{I}result, ok = jsonable.(string)
{I}if ok {{
{II}return
{I}}} else {{
{II}err = newDeserializationError(
{III}fmt.Sprintf("Expected a string, but got %T", jsonable),
{II})
{II}return
{I}}}
}}"""
    )


def _generate_bytes_from_jsonable() -> Stripped:
    """Generate the function to decode ``[]byte`` from a JSON-able."""
    return Stripped(
        f"""\
// Parse `jsonable` as a byte array, or return an error.
func bytesFromJsonable(
{I}jsonable interface{{}},
) (result []byte, err error) {{
{I}if jsonable == nil {{
{II}err = newDeserializationError(
{III}"Expected a base64-encoded string, but got null",
{II})
{II}return
{I}}}

{I}text, ok := jsonable.(string)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a base64-encoded string, but got %T",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

{I}var decodingErr error
{I}result, decodingErr = b64.StdEncoding.DecodeString(text)
{I}if decodingErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"String could not be decoded as base64: %s",
{IIII}decodingErr.Error(),
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_parse_array() -> Stripped:
    """Generate the generic helper to parse a JSON array item-by-item."""
    return Stripped(
        f"""\
// Parse `jsonableArray` into a slice of `T` by calling `parseItem` on every
// item, or return an error.
func parseArray[T any](
{I}jsonableArray []interface{{}},
{I}parseItem func(jsonable interface{{}}) (T, error),
) (result []T, err error) {{
{I}result = make([]T, len(jsonableArray))
{I}for i, itemJsonable := range jsonableArray {{
{II}var item T
{II}item, err = parseItem(itemJsonable)
{II}if err != nil {{
{III}if deseriaErr, ok := err.(*DeserializationError); ok {{
{IIII}deseriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{Index: i}},
{IIII})
{III}}}
{III}return
{II}}}
{II}result[i] = item
{I}}}
{I}return
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_parse_tuple_helper(arity: int) -> Stripped:
    """
    Generate a generic function to parse a tuple of the given ``arity``.

    Every atomic value parser already has the uniform signature
    ``func(jsonable interface{}) (T, error)`` (the very same shape
    :py:func:`_generate_parse_array` expects for a list item), so -- unlike
    XML, where a tuple item additionally needs a positional element name
    bound in -- a tuple item's parser can be passed on to the generated
    function as a bare reference, with no adapter or closure needed.
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(f"{t} any" for t in type_params)

    tuple_type = f"aascommon.Tuple{arity}[{', '.join(type_params)}]"

    params_joined = ",\n".join(
        f"parseItem{i} func(jsonable interface{{}}) ({type_params[i]}, error)"
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
var item{i} {type_params[i]}
item{i}, err = parseItem{i}(jsonableArray[{i}])
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{Index: {i}}},
{II})
{I}}}
{I}return
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    item_fields_joined = ",\n".join(f"Item{i + 1}: item{i}" for i in range(arity))

    function_name = f"parseTuple{arity}"

    return Stripped(
        f"""\
// Parse `jsonableArray` into a {tuple_type} by calling `parseItem0`,
// `parseItem1`, *etc.* on the correspondingly positioned item, or return
// an error.
func {function_name}[{type_params_joined}](
{I}jsonableArray []interface{{}},
{I}{indent_but_first_line(params_joined, I)},
) (result {tuple_type}, err error) {{
{I}if len(jsonableArray) != {arity} {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected exactly {arity} item(s), but got: %d",
{IIII}len(jsonableArray),
{III}),
{II})
{II}return
{I}}}

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}result = {tuple_type}{{
{II}{indent_but_first_line(item_fields_joined, II)},
{I}}}
{I}return
}}"""
    )


def _generate_enumeration_from_jsonable(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the deserialization method for an enumeration."""
    enum_name = golang_naming.enum_name(identifier=enumeration.name)

    function_name = golang_naming.function_name(
        Identifier(f"{enumeration.name}_from_jsonable")
    )

    enum_from_str = golang_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    return Stripped(
        f"""\
// Parse `jsonable` as a literal of [aastypes.{enum_name}],
// or return an error.
func {function_name}(
{I}jsonable interface{{}},
) (result aastypes.{enum_name}, err error) {{
{I}if jsonable == nil {{
{II}err = newDeserializationError(
{III}"Expected a string representation of {enum_name}, " +
{III}"but got null",
{II})
{II}return
{I}}}

{I}text, ok := jsonable.(string)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a string representation of {enum_name}, " +
{IIII}"but got %T",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

{I}result, ok = aasstringification.{enum_from_str}(text)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a string representation of {enum_name}, " +
{IIII}"but got %v",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


# fmt: off
@require(
    lambda cls:
    len(cls.concrete_descendants) > 0,
    "A class that needs dispatch must have more than one concrete descendant"
)
# fmt: on
def _generate_class_from_map(cls: intermediate.ClassUnion) -> Stripped:
    """Generate a mapping model type 🠒 de-serialization from map."""
    model_types_dispatch_names = []  # type: List[Tuple[str, str]]

    for descendant in cls.concrete_descendants:
        model_types_dispatch_names.append(
            (
                naming.json_model_type(descendant.name),
                golang_naming.private_function_name(
                    Identifier(f"{descendant.name}_from_map_without_dispatch")
                ),
            )
        )

    if isinstance(cls, intermediate.ConcreteClass):
        model_types_dispatch_names.append(
            (
                naming.json_model_type(cls.name),
                golang_naming.private_function_name(
                    Identifier(f"{cls.name}_from_map_without_dispatch")
                ),
            )
        )

    case_blocks = []  # type: List[Stripped]
    for model_type, dispatch_name in model_types_dispatch_names:
        model_type_literal = golang_common.string_literal(model_type)
        case_blocks.append(
            Stripped(
                f"""\
case {model_type_literal}:
{I}result, err = {dispatch_name}(m)"""
            )
        )

    interface_name = golang_naming.interface_name(cls.name)

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected model type " +
{III}"for {interface_name}: %s",
{III}modelType,
{II}),
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    function_name = golang_naming.private_function_name(
        Identifier(f"{cls.name}_from_map")
    )

    return Stripped(
        f"""\
// De-serialize an instance of [aastypes.{interface_name}]
// from a map by dispatching to the concrete `*FromMapWithoutDispatch` function.
func {function_name}(
{I}m map[string]interface{{}},
) (
{I}result aastypes.{interface_name},
{I}err error,
) {{
{I}var modelTypeAny interface{{}}
{I}var ok bool
{I}modelTypeAny, ok = m["modelType"];
{I}if !ok {{
{II}err = newDeserializationError(
{III}"The required property modelType is missing",
{II})
{II}return
{I}}}

{I}var modelType string
{I}modelType, ok = modelTypeAny.(string)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected the property modelType to be a string, " +
{IIII}"but got %T",
{IIII}modelTypeAny,
{III}),
{II})
{II}return
{I}}}

{I}switch modelType {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}

{I}return
}}"""
    )


def _generate_class_from_jsonable(cls: intermediate.ClassUnion) -> Stripped:
    """Generate the de-serialization function for a class that involves a dispatch."""
    function_name = golang_naming.function_name(Identifier(f"{cls.name}_from_jsonable"))

    interface_name = golang_naming.interface_name(cls.name)

    blocks = [
        Stripped(
            f"""\
if jsonable == nil {{
{I}err = newDeserializationError(
{II}"Expected a JSON object, but got null",
{I})
{I}return
}}"""
        ),
        Stripped(
            f"""\
m, ok := jsonable.(map[string]interface{{}})
if !ok {{
{I}err = newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected a JSON object, but got %T",
{III}jsonable,
{II}),
{I})
{I}return
}}"""
        ),
    ]  # type: List[Stripped]

    if len(cls.concrete_descendants) == 0:
        assert not isinstance(cls, intermediate.AbstractClass), (
            "We can not parse abstract classes without any concrete descendants "
            "as we do not know the concrete structure of the map."
        )

        from_map_name = golang_naming.private_function_name(
            Identifier(f"{cls.name}_from_map_without_dispatch")
        )
    else:
        from_map_name = golang_naming.private_function_name(
            Identifier(f"{cls.name}_from_map")
        )

    blocks.append(Stripped(f"result, err = {from_map_name}(m)"))
    blocks.append(Stripped("return"))

    body = Stripped("\n\n".join(blocks))

    return Stripped(
        f"""\
// Parse `jsonable` as an instance of [aastypes.{interface_name}],
// or return an error.
func {function_name}(
{I}jsonable interface{{}},
) (
{I}result aastypes.{interface_name},
{I}err error,
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


_PARSE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "boolFromJsonable",
    intermediate.PrimitiveType.INT: "int64FromJsonable",
    intermediate.PrimitiveType.FLOAT: "float64FromJsonable",
    intermediate.PrimitiveType.STR: "stringFromJsonable",
    intermediate.PrimitiveType.BYTEARRAY: "bytesFromJsonable",
}
assert all(
    literal in _PARSE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _determine_parse_function_for_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """Determine the parse function for deserializing an atomic non-optional value."""
    function_name: str

    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        function_name = _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            function_name = golang_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            function_name = _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[our_type.constrainee]

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            function_name = golang_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        else:
            # noinspection PyTypeChecker
            assert_never(our_type)
    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)

    return Stripped(function_name)


def _generate_deserialization_switch_statement(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the switch statement for de-serialization of the properties.

    This statement is expected to be run in a ``for k, v := range m`` loop.
    We switch on ``k`` and the value of the property is given as ``v``. The ``jsonable``
    is expected to be of type ``map[string]interface{}``.

    The resulting struct we parse into is ``result``, a pointer to the struct
    corresponding to ``cls``. Whenever we encounter a property, we have to set
    the corresponding boolean ``found*`` to ``True``.

    This function was originally part of
    ``_generate_concrete_class_from_map_without_dispatch``, but we refactored it out
    since it was too much to read. Best if your read both functions in two vertical
    editor panes.

    If the serialization requires model type, we also expect that the variable
    ``foundModelType`` have been initialized as a ``bool`` in the preceding generated
    code. The generated case block will parse and set it in case that the model type
    is correctly specified. This will be performed even though the code might have
    had to parse model type before for the dispatch. We decided to double-check to cover
    the case where a dispatch is *unnecessary* (*e.g.*, the caller knows the expected
    runtime type), but the model type might still be invalid in the input. Hence, when
    the dispatch is *necessary*, the model type JSON property will be parsed twice,
    which is a cost we currently find acceptable.
    """
    case_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        json_prop_literal = golang_common.string_literal(prop.json_name)

        case_body: Stripped

        primitive_type = intermediate.try_primitive_type(type_anno)

        # NOTE (mristin):
        # We handle this case of the atomic value separately from the others as
        # we model the optional values with pointers, so we first have to parse into
        # a value, and then pass a pointer to that value to the property of
        # the instance.
        if optional and (
            (
                primitive_type is not None
                and primitive_type is not intermediate.PrimitiveType.BYTEARRAY
            )
            or (
                isinstance(type_anno, intermediate.OurTypeAnnotation)
                and isinstance(type_anno.our_type, intermediate.Enumeration)
            )
        ):
            assert isinstance(
                type_anno,
                (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
            )
            parse_function = _determine_parse_function_for_atomic_value(type_anno)

            value_type = golang_common.generate_type(
                type_annotation=type_anno, types_package=Identifier("aastypes")
            )

            case_body = Stripped(
                f"""\
var parsed {value_type}
parsed, err = {parse_function}(
{I}v,
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {json_prop_literal},
{III}}},
{II})
{I}}}
{I}return
}}
{prop_var} = &parsed"""
            )

        elif isinstance(
            type_anno,
            (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
        ):
            parse_function = _determine_parse_function_for_atomic_value(type_anno)

            case_body = Stripped(
                f"""\
{prop_var}, err = {parse_function}(
{I}v,
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {json_prop_literal},
{III}}},
{II})
{I}}}
{I}return
}}"""
            )

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We expect only lists of atomic types "
                f"at the moment, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            parse_function = _determine_parse_function_for_atomic_value(type_anno.items)

            case_body = Stripped(
                f"""\
jsonableArray, ok := v.([]interface{{}})
if !ok {{
{I}deseriaErr := newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected an array, but got %T",
{III}v,
{II}),
{I})

{I}deseriaErr.Path.PrependName(
{II}&aasreporting.NameSegment{{
{III}Name: {json_prop_literal},
{II}}},
{I})

{I}err = deseriaErr

{I}return
}}

{prop_var}, err = parseArray(
{I}jsonableArray,
{I}{parse_function},
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {json_prop_literal},
{III}}},
{II})
{I}}}

{I}return
}}"""
            )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            arity = len(type_anno.items)

            parse_functions = []  # type: List[str]
            for item_type_anno in type_anno.items:
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"NOTE (mristin): We expect only atomic items in a tuple "
                    f"at the moment, but got {item_type_anno} in {type_anno}. "
                    f"This should have already been verified in "
                    f"intermediate._translate._verify_only_simple_type_patterns."
                )

                parse_functions.append(
                    _determine_parse_function_for_atomic_value(item_type_anno)
                )

            parse_functions_joined = "\n".join(f"{fn}," for fn in parse_functions)

            case_body = Stripped(
                f"""\
jsonableArray, ok := v.([]interface{{}})
if !ok {{
{I}deseriaErr := newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected an array, but got %T",
{III}v,
{II}),
{I})

{I}deseriaErr.Path.PrependName(
{II}&aasreporting.NameSegment{{
{III}Name: {json_prop_literal},
{II}}},
{I})

{I}err = deseriaErr

{I}return
}}

{prop_var}, err = parseTuple{arity}(
{I}jsonableArray,
{I}{indent_but_first_line(parse_functions_joined, I)}
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {json_prop_literal},
{III}}},
{II})
{I}}}

{I}return
}}"""
            )

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        if not optional:
            found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

            # NOTE (mristin):
            # Appending once is OK for time complexity. If you append more, please
            # refactor into a list and join.
            case_body = Stripped(
                f"""\
{case_body}
{found_var} = true"""
            )

        case_blocks.append(
            Stripped(
                f"""\
case {json_prop_literal}:
{I}{indent_but_first_line(case_body, I)}"""
            )
        )

    if cls.serialization.with_model_type:
        # NOTE (mristin):
        # We explicitly check for the model type if the meta-model instructs us to.
        #
        # This is crucial for the fix of the problem discovered in:
        # https://github.com/aas-core-works/aas-core3.0-python/issues/32
        model_type = naming.json_model_type(cls.name)
        model_type_case_body = Stripped(
            f"""\
var modelType string
modelType, err = stringFromJsonable(
{I}v,
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: "modelType",
{III}}},
{II})
{I}}}
{I}return
}}

if modelType != "{model_type}" {{
{I}deseriaErr := newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected the model type '{model_type}', but got %v",
{III}v,
{II}),
{I})

{I}deseriaErr.Path.PrependName(
{II}&aasreporting.NameSegment{{
{III}Name: "modelType",
{II}}},
{I})

{I}err = deseriaErr
{I}return
}}

foundModelType = true"""
        )
        case_blocks.append(
            Stripped(
                f"""\
case "modelType":
{I}{indent_but_first_line(model_type_case_body, I)}"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected property: %s",
{III}k,
{II}),
{I})
{I}return"""
        )
    )

    case_blocks_joined = "\n\n".join(case_blocks)

    return Stripped(
        f"""\
switch k {{
{case_blocks_joined}
}}"""
    )


def _generate_concrete_class_from_map_without_dispatch(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the deserialization function for a concrete class from a map.

    This function performs no dispatch. If it de-serializes a concrete class with
    concrete descendants, we have to provide a different name. Otherwise, it would
    shadow the name for the dispatch function.
    """
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
                (prop.name, str(prop.type_annotation))
                for prop in cls.properties
            )
    ), (
        "(mristin, 2023-04-07) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    blocks = []  # type: List[Stripped]

    # region Initialize

    prop_var_initializations = []  # type: List[Stripped]
    for prop in cls.properties:
        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        prop_var_type = golang_common.generate_type(
            type_annotation=prop.type_annotation, types_package=Identifier("aastypes")
        )

        prop_var_initializations.append(Stripped(f"var {prop_var} {prop_var_type}"))

    if len(prop_var_initializations) > 0:
        blocks.append(Stripped("\n".join(prop_var_initializations)))

    found_var_initializations = []  # type: List[Stripped]
    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

        found_var_initializations.append(Stripped(f"{found_var} := false"))

    if len(found_var_initializations) > 0:
        blocks.append(Stripped("\n".join(found_var_initializations)))

    # endregion

    # NOTE (mristin):
    # We explicitly check for the model type if the meta-model instructs us to.
    #
    # This is crucial for the fix of the problem discovered in:
    # https://github.com/aas-core-works/aas-core3.0-python/issues/32
    if cls.serialization.with_model_type:
        blocks.append(Stripped("var foundModelType bool"))

    # region Switch on property name

    switch_statement = _generate_deserialization_switch_statement(cls=cls)

    # endregion

    # NOTE (mristin):
    # ``v`` is only referenced in the case branches of the switch statement, which
    # only exist for the actual properties and, if applicable, the model type
    # discriminator. If neither is present, ``v`` would be declared, but never used,
    # which Go rejects at compile time.
    if len(cls.properties) > 0 or cls.serialization.with_model_type:
        blocks.append(
            Stripped(
                f"""\
for k, v := range m {{
{I}{indent_but_first_line(switch_statement, I)}
}}"""
            )
        )
    else:
        blocks.append(
            Stripped(
                f"""\
for k := range m {{
{I}{indent_but_first_line(switch_statement, I)}
}}"""
            )
        )

    # region Check required properties

    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

        message_literal = golang_common.string_literal(
            f"The required property {prop.json_name!r} is missing"
        )

        blocks.append(
            Stripped(
                f"""\
if !{found_var} {{
{I}err = newDeserializationError(
{II}{message_literal},
{I})
{I}return
}}"""
            )
        )

    # endregion

    if cls.serialization.with_model_type:
        # NOTE (mristin):
        # We explicitly check for the model type if the meta-model instructs us to.
        #
        # This is crucial for the fix of the problem discovered in:
        # https://github.com/aas-core-works/aas-core3.0-python/issues/32
        blocks.append(
            Stripped(
                f"""\
if !foundModelType {{
{I}err = newDeserializationError(
{II}"The required property modelType is missing",
{I})
{I}return
}}"""
            )
        )

    constructing_statements = []  # type: List[Stripped]

    constructor_arguments = [
        golang_naming.variable_name(Identifier(f"the_{arg.name}"))
        for arg in cls.constructor.arguments
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
    ]  # type: List[Stripped]

    new_function = golang_naming.function_name(Identifier(f"new_{cls.name}"))

    if len(constructor_arguments) > 0:
        constructor_arguments_joined = "\n".join(
            f"{arg}," for arg in constructor_arguments
        )

        constructing_statements.append(
            Stripped(
                f"""\
result = aastypes.{new_function}(
{I}{indent_but_first_line(constructor_arguments_joined, I)}
)"""
            )
        )
    else:
        constructing_statements.append(Stripped(f"result = aastypes.{new_function}()"))

    for arg in cls.constructor.arguments:
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        setter_name = golang_naming.setter_name(arg.name)
        prop_var = golang_naming.variable_name(Identifier(f"the_{arg.name}"))

        constructing_statements.append(
            Stripped(
                f"""\
result.{setter_name}(
{I}{prop_var},
)"""
            )
        )

    blocks.append(Stripped("\n".join(constructing_statements)))

    blocks.append(Stripped("return"))

    body = Stripped("\n\n".join(blocks))

    interface_name = golang_naming.interface_name(cls.name)

    function_name = golang_naming.private_function_name(
        Identifier(f"{cls.name}_from_map_without_dispatch")
    )

    documentation_blocks = [
        Stripped(
            f"""\
Parse [aastypes.{interface_name}] from a map,
or return an error, if any."""
        )
    ]  # type: List[Stripped]

    if len(cls.concrete_descendants) > 0:
        function_name_from_jsonable = golang_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )

        documentation_blocks.append(
            Stripped(
                f"""\
This function performs no dispatch! It is used to parse the properties
as-are, and already assumes the exact model type. Usually, this function
is called from within a from-jsonable or from-map function, and you never
call it directly. If you want to de-serialize an instance of
[aastypes.{interface_name}], call
[{function_name_from_jsonable}]."""
            )
        )

    documentation_comment = golang_description.documentation_comment(
        Stripped("\n\n".join(documentation_blocks))
    )

    return Stripped(
        f"""\
{documentation_comment}
func {function_name}(
{I}m map[string]interface{{}},
) (
{I}result aastypes.{interface_name},
{I}err error,
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


# endregion

# region Serialization


def _generate_int64_to_jsonable() -> Stripped:
    """Generate the function to encode an ``int64`` to a JSON-able."""
    return Stripped(
        f"""\
// Try to cast `that` to a float64 and box it as a JSON-able value, or
// return an error.
//
// The result is returned as `interface{{}}`, not the more specific
// `float64`, so that this function itself can be passed on as a bare
// reference wherever a `func(int64) (interface{{}}, error)` is expected,
// e.g. as an item (de)serializer in a list or a tuple.
func int64ToJsonable(
{I}that int64,
) (result interface{{}}, err error) {{
{I}if that > 9007199254740991 || that < -9007199254740991 {{
{II}err = newSerializationError(
{III}fmt.Sprintf(
{IIII}"64-bit integer can not be represented as 64-bit float in JSON: %v",
{IIII}that,
{III}),
{II})
{II}return
{I}}}

{I}result = float64(that);
{I}return
}}"""
    )


def _generate_bytes_to_jsonable() -> Stripped:
    """Generate the function to encode ``[]byte`` to a string."""
    return Stripped(
        f"""\
// Encode `bytes` to a base64 string and box it as a JSON-able value, or
// return an error.
//
// The result is returned as `interface{{}}`, not the more specific
// `string`, so that this function itself can be passed on as a bare
// reference wherever a `func([]byte) (interface{{}}, error)` is expected,
// e.g. as an item (de)serializer in a list or a tuple.
func bytesToJsonable(
{I}bytes []byte,
) (result interface{{}}, err error) {{
{I}if bytes == nil {{
{II}err = newSerializationError(
{III}"Expected an array of bytes, but got nil",
{II})
{II}return
{I}}}

{I}result = b64.StdEncoding.EncodeToString(
{II}bytes,
{I})
{I}return
}}"""
    )


def _generate_serialize_array() -> Stripped:
    """Generate the generic helper to serialize a slice into a JSON array."""
    return Stripped(
        f"""\
// Serialize every item of `items` with `serializeItem` into a JSON-able array,
// or return an error.
func serializeArray[T any](
{I}items []T,
{I}serializeItem func(item T) (interface{{}}, error),
) (result []interface{{}}, err error) {{
{I}result = make([]interface{{}}, len(items))
{I}for i, item := range items {{
{II}var jsonable interface{{}}
{II}jsonable, err = serializeItem(item)
{II}if err != nil {{
{III}if seriaErr, ok := err.(*SerializationError); ok {{
{IIII}seriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{Index: i}},
{IIII})
{III}}}
{III}return
{II}}}
{II}result[i] = jsonable
{I}}}
{I}return
}}"""
    )


def _generate_direct_to_jsonable() -> Stripped:
    """
    Generate the generic function to forward a value as a JSON-able as-is.

    ``serializeTupleN`` (see :py:func:`_generate_serialize_tuple_helper`)
    accepts a plain ``func(item T) (interface{}, error)`` per item, so a
    tuple item whose serialization already resolves to a single named
    function of ours with exactly that shape can be passed on directly, with
    no wrapping closure -- see :py:func:`_tuple_item_serializer_function`.

    A ``bool``/``float64``/``string`` item needs no conversion at all in
    Go's JSON representation, so this generic identity-like function stands
    in for those directly, instead of a closure repeated at every such tuple
    item.
    """
    return Stripped(
        f"""\
// Forward `item` as a JSON-able value, unconverted.
func directToJsonable[T any](item T) (interface{{}}, error) {{
{I}return item, nil
}}"""
    )


def _generate_class_as_jsonable_interface() -> Stripped:
    """Generate the wrapper so a class tuple item is a bare function reference."""
    return Stripped(
        f"""\
// Serialize `that` to a JSON-able value, or return an error.
//
// `ToJsonable` takes an `aastypes.IClass`, but a tuple item's own
// (more specific) interface type, e.g., `aastypes.ISomeItem`, can not be
// unified with that when passing `ToJsonable` itself as a
// `func(item T) (interface{{}}, error)` value -- Go function values are
// invariant in their parameter type (no contravariance, unlike, say, a C#
// delegate). Making this wrapper itself generic (instead of fixing its
// parameter to `aastypes.IClass`) lets the very same one be passed on bare,
// uninstantiated, for every class-typed tuple item regardless of its
// concrete interface: Go infers both the tuple item's type and this
// wrapper's own type parameter together from the context of the
// `serializeTupleN` call.
func classAsJsonableInterface[T aastypes.IClass](that T) (interface{{}}, error) {{
{I}return ToJsonable(that)
}}"""
    )


def _generate_enum_as_jsonable_interface(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the wrapper so an enum tuple item is a bare function reference."""
    enum_name = golang_naming.enum_name(identifier=enumeration.name)

    to_jsonable = golang_naming.function_name(
        Identifier(f"{enumeration.name}_to_jsonable")
    )

    function_name = golang_naming.private_function_name(
        Identifier(f"{enumeration.name}_as_jsonable_interface")
    )

    return Stripped(
        f"""\
// Serialize `that` to a JSON-able value, or return an error.
//
// `{to_jsonable}` returns `(string, error)`, not `(interface{{}}, error)` --
// Go function values require an exact signature match (no covariance), so
// it can not be passed on directly wherever a `func(item T) (interface{{}},
// error)` is expected, e.g. as an item serializer in a tuple. This wrapper
// exists solely to have the right signature.
func {function_name}(that aastypes.{enum_name}) (interface{{}}, error) {{
{I}return {to_jsonable}(that)
}}"""
    )


def _tuple_item_serializer_function(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """
    Determine the function reference to serialize a tuple item.

    ``directToJsonable`` and ``classAsJsonableInterface`` are themselves
    generic, so -- exactly as for ``asInstanceTupleItemWriter`` in XML
    de/serialization (see :py:func:`_generate_as_instance_tuple_item_writer`
    in ``_generate_xmlization.py``) -- we have to instantiate them
    explicitly at every call site with the item's own Go type. Go can not
    infer the type parameter for a generic function passed on as a bare,
    uncalled value without ``go1.21``, and this project intentionally
    targets ``go1.18``.
    """
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        primitive_type = type_annotation.a_type
    elif isinstance(type_annotation, intermediate.OurTypeAnnotation) and isinstance(
        type_annotation.our_type, intermediate.ConstrainedPrimitive
    ):
        primitive_type = type_annotation.our_type.constrainee
    else:
        primitive_type = None

    if primitive_type is not None:
        if primitive_type is intermediate.PrimitiveType.INT:
            return Stripped("int64ToJsonable")
        elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            return Stripped("bytesToJsonable")
        else:
            # NOTE (mristin):
            # The remaining primitive types (BOOL, FLOAT, STR) all share the
            # same ``directToJsonable`` reference -- we deliberately do
            # not enumerate them explicitly with ``assert_never`` at the end,
            # since mypy can not narrow a literal type through ``in``
            # membership tests the way it can through ``isinstance``.
            item_type = golang_common.generate_type(
                type_annotation=type_annotation, types_package=Identifier("aastypes")
            )
            return Stripped(f"directToJsonable[{item_type}]")

    assert isinstance(type_annotation, intermediate.OurTypeAnnotation)
    our_type = type_annotation.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return golang_naming.private_function_name(
            Identifier(f"{our_type.name}_as_jsonable_interface")
        )
    elif isinstance(our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)):
        item_type = golang_common.generate_type(
            type_annotation=type_annotation, types_package=Identifier("aastypes")
        )
        return Stripped(f"classAsJsonableInterface[{item_type}]")
    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        raise AssertionError(
            f"Unexpected {our_type=}: a constrained primitive should have "
            f"already been handled above through ``primitive_type``"
        )
    else:
        assert_never(our_type)


@require(lambda arity: arity > 0)
def _generate_serialize_tuple_helper(arity: int) -> Stripped:
    """Generate a generic function to serialize a tuple of the given ``arity``."""
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(f"{t} any" for t in type_params)

    tuple_type = f"aascommon.Tuple{arity}[{', '.join(type_params)}]"

    params_joined = ",\n".join(
        f"serializeItem{i} func(item {type_params[i]}) (interface{{}}, error)"
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
var jsonable{i} interface{{}}
jsonable{i}, err = serializeItem{i}(that.Item{i + 1})
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{Index: {i}}},
{II})
{I}}}
{I}return
}}
result[{i}] = jsonable{i}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    function_name = f"serializeTuple{arity}"

    return Stripped(
        f"""\
// Serialize `that` with `serializeItem0`, `serializeItem1`, *etc.* into
// a JSON-able array, or return an error.
func {function_name}[{type_params_joined}](
{I}that {tuple_type},
{I}{indent_but_first_line(params_joined, I)},
) (result []interface{{}}, err error) {{
{I}result = make([]interface{{}}, {arity})

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return
}}"""
    )


def _generate_enumeration_to_jsonable(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the serialization method for an enumeration."""
    enum_name = golang_naming.enum_name(identifier=enumeration.name)

    function_name = golang_naming.function_name(
        Identifier(f"{enumeration.name}_to_jsonable")
    )

    enum_to_str = golang_naming.function_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    return Stripped(
        f"""\
// Serialize `that` to a string, or return an error.
func {function_name}(
{I}that aastypes.{enum_name},
) (result string, err error) {{
{I}var ok bool
{I}result, ok = aasstringification.{enum_to_str}(
{II}that,
{I})
{I}if !ok {{
{II}err = newSerializationError(
{III}fmt.Sprintf(
{IIII}"Got an invalid literal of {enum_name}: %v",
{IIII}that,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


TypeAnnotationExceptList = Union[
    intermediate.PrimitiveTypeAnnotation,
    intermediate.OurTypeAnnotation,
    intermediate.OptionalTypeAnnotation,
]

assert_union_without_excluded(
    original_union=intermediate.TypeAnnotationUnion,
    subset_union=TypeAnnotationExceptList,
    # NOTE (mristin, 2026-09-03):
    # ``ListTypeAnnotation`` and ``TupleTypeAnnotation`` are handled directly in
    # the calling code (see ``_generate_cls_to_map``), which unrolls them into
    # calls of this function on the atomic items.
    excluded=[intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation],
)


def _generate_expression_to_serialize_atomic_value(
    access_expression: str, type_annotation: TypeAnnotationExceptList
) -> Tuple[Stripped, bool]:
    """
    Generate the snippet to serialize the ``access_expression``.

    The ``access_expression`` is for example a name or a property access.
    The caller is expected to have already generated the code which checks that
    ``access_expression`` is not nil.

    Return (expression, True if there needs to be error checking)
    """
    type_anno = intermediate.beneath_optional(type_annotation)
    assert isinstance(
        type_anno,
        (
            intermediate.PrimitiveTypeAnnotation,
            intermediate.OurTypeAnnotation,
        ),
    )

    optional = isinstance(type_annotation, intermediate.OptionalTypeAnnotation)

    # NOTE (mristin, 2023-04-12):
    # The following types are handled as primitive values in Golang, so we have
    # to handle them as such. They are primitive values if non-nullable, and referenced
    # if nullable, since we model optional primitive properties as pointers in
    # Golang.
    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(
            type_anno.our_type,
            (intermediate.Enumeration, intermediate.ConstrainedPrimitive),
        )
    ):
        primitive_type = intermediate.try_primitive_type(type_anno)

        if primitive_type is intermediate.PrimitiveType.INT:
            if not optional:
                return (
                    Stripped(
                        f"""\
int64ToJsonable(
{I}{access_expression},
)"""
                    ),
                    True,
                )
            else:
                return (
                    Stripped(
                        f"""\
int64ToJsonable(
{I}*({access_expression}),
)"""
                    ),
                    True,
                )

        elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            return (
                Stripped(
                    f"""\
bytesToJsonable(
{I}{access_expression},
)"""
                ),
                True,
            )

        elif isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type, intermediate.Enumeration
        ):
            enumeration = type_anno.our_type
            enum_to_jsonable = golang_naming.function_name(
                Identifier(f"{enumeration.name}_to_jsonable")
            )

            if not optional:
                return (
                    Stripped(
                        f"""\
{enum_to_jsonable}(
{I}{access_expression},
)"""
                    ),
                    True,
                )
            else:
                return (
                    Stripped(
                        f"""\
{enum_to_jsonable}(
{I}*({access_expression}),
)"""
                    ),
                    True,
                )
        else:
            if optional:
                return Stripped(f"*{access_expression}"), False
            else:
                return Stripped(access_expression), False

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            raise AssertionError(f"Should have been handled before: {type_anno=}")

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError(f"Should have been handled before: {type_anno=}")

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            return (
                Stripped(
                    f"""\
ToJsonable(
{I}{access_expression},
)"""
                ),
                True,
            )

        else:
            # noinspection PyTypeChecker
            assert_never(our_type)
    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)


def _generate_cls_to_map(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the function to serialize class to a JSON-able map.

    The generated function will perform no dispatching.
    """
    blocks = [Stripped("result = make(map[string]interface{})")]  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        getter_name = golang_naming.getter_name(prop.name)

        prop_literal = golang_common.string_literal(
            f"{golang_naming.property_name(prop.name)}()"
        )

        json_prop_literal = golang_common.string_literal(prop.json_name)

        prop_jsonable_var = golang_naming.variable_name(
            Identifier(f"jsonable_{prop.name}")
        )

        block: Stripped

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "(mristin): We currently generate only the code to serialize lists of "
                "atomic values. If you need this feature, please contact "
                "the developers."
            )

            item_type = golang_common.generate_type(
                type_annotation=type_anno.items, types_package=Identifier("aastypes")
            )

            # NOTE (mristin):
            # ``int64ToJsonable`` and ``bytesToJsonable`` already have the exact
            # signature ``func(item T) (interface{}, error)`` that ``serializeArray``
            # expects, so they can be passed on as a bare function reference. Every
            # other item type still needs a closure below to adapt its
            # serialization expression to that signature.
            item_primitive_type = intermediate.try_primitive_type(type_anno.items)

            item_serializer_arg: Stripped
            if item_primitive_type is intermediate.PrimitiveType.INT:
                item_serializer_arg = Stripped("int64ToJsonable")
            elif item_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                item_serializer_arg = Stripped("bytesToJsonable")
            else:
                # fmt: off
                serialize_expr, needs_error_checking = (
                    _generate_expression_to_serialize_atomic_value(
                        access_expression="item", type_annotation=type_anno.items
                    )
                )
                # fmt: on

                if needs_error_checking:
                    closure_body = Stripped(f"return {serialize_expr}")
                else:
                    closure_body = Stripped(f"return {serialize_expr}, nil")

                item_serializer_arg = Stripped(
                    f"""\
func(item {item_type}) (interface{{}}, error) {{
{I}{indent_but_first_line(closure_body, I)}
}}"""
                )

            block = Stripped(
                f"""\
var {prop_jsonable_var} []interface{{}}
{prop_jsonable_var}, err = serializeArray(
{I}that.{getter_name}(),
{I}{indent_but_first_line(item_serializer_arg, I)},
)
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_literal},
{III}}},
{II})
{I}}}

{I}return
}}
result[{json_prop_literal}] = {prop_jsonable_var}"""
            )
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            arity = len(type_anno.items)

            serialize_functions = []  # type: List[str]
            for item_type_anno in type_anno.items:
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"NOTE (mristin): We expect only atomic items in a tuple "
                    f"at the moment, but got {item_type_anno} in {type_anno}. "
                    f"This should have already been verified in "
                    f"intermediate._translate._verify_only_simple_type_patterns."
                )

                serialize_functions.append(
                    _tuple_item_serializer_function(item_type_anno)
                )

            serialize_functions_joined = "\n".join(
                f"{fn}," for fn in serialize_functions
            )

            block = Stripped(
                f"""\
var {prop_jsonable_var} []interface{{}}
{prop_jsonable_var}, err = serializeTuple{arity}(
{I}that.{getter_name}(),
{I}{indent_but_first_line(serialize_functions_joined, I)}
)
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_literal},
{III}}},
{II})
{I}}}

{I}return
}}
result[{json_prop_literal}] = {prop_jsonable_var}"""
            )
        else:
            assert isinstance(
                prop.type_annotation,
                (
                    intermediate.PrimitiveTypeAnnotation,
                    intermediate.OurTypeAnnotation,
                    intermediate.OptionalTypeAnnotation,
                ),
            ), (
                f"Since {type_anno} is neither a list nor a tuple, "
                f"we expect the property to be atomic (optionally wrapped), "
                f"but got {prop.type_annotation}."
            )

            # fmt: off
            serialize_expr, needs_error_checking = (
                _generate_expression_to_serialize_atomic_value(
                    access_expression=f"that.{getter_name}()",
                    type_annotation=prop.type_annotation
                )
            )
            # fmt: on

            if needs_error_checking:
                block = Stripped(
                    f"""\
var {prop_jsonable_var} interface{{}}
{prop_jsonable_var}, err = {serialize_expr}
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependName(
{III}&aasreporting.NameSegment{{
{IIII}Name: {prop_literal},
{III}}},
{II})
{I}}}

{I}return
}}
result[{json_prop_literal}] = {prop_jsonable_var}"""
                )
            else:
                block = Stripped(
                    f"""\
result[{json_prop_literal}] = {serialize_expr}"""
                )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if that.{getter_name}() != nil {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

    if cls.serialization.with_model_type:
        model_type_literal = golang_common.string_literal(
            naming.json_model_type(cls.name)
        )
        blocks.append(Stripped(f'result["modelType"] = {model_type_literal}'))

    blocks.append(Stripped("return"))

    body = "\n\n".join(blocks)

    function_name = golang_naming.private_function_name(
        Identifier(f"{cls.name}_to_map")
    )

    interface_name = golang_naming.interface_name(cls.name)

    to_jsonable = golang_naming.function_name(Identifier("to_jsonable"))

    return Stripped(
        f"""\
// Serialize [aastypes.{interface_name}] as a JSON-able map.
//
// This function performs no dispatch! It is only used to serialize
// the properties. If you want to serialize an instance of
// [aastypes.{interface_name}] with proper dispatch, call
// [{to_jsonable}].
func {function_name}(
{I}that aastypes.{interface_name},
) (result map[string]interface{{}}, err error) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_to_jsonable(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the main entry point for the serialization."""
    case_blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        interface_name = golang_naming.interface_name(cls.name)

        to_map = golang_naming.private_function_name(Identifier(f"{cls.name}_to_map"))

        case_blocks.append(
            Stripped(
                f"""\
case aastypes.{literal}:
{I}result, err = {to_map}(
{II}that.(aastypes.{interface_name}),
{I})"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newSerializationError(
{II}fmt.Sprintf(
{III}"Unexpected model type literal: %v",
{III}that.ModelType(),
{II}),
{I})"""
        )
    )

    switch_body = Stripped("\n".join(case_blocks))
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))
    switch_statement = Stripped(
        f"""\
switch that.{model_type_getter}() {{
{switch_body}
}}"""
    )

    return Stripped(
        f"""\
// Serialize “that“ instance to a JSON-able representation.
//
// Return a structure which can be readily converted to JSON,
// or an error if some value could not be converted.
func ToJsonable(
{I}that aastypes.IClass,
) (result map[string]interface{{}}, err error) {{
{I}{indent_but_first_line(switch_statement, I)}
{I}return
}}"""
    )


# endregion

# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for JSON de/serialization."""
    aastypes_url_literal = golang_common.string_literal(f"{repo_url}/types")

    aascommon_url_literal = golang_common.string_literal(f"{repo_url}/common")

    aasreporting_url_literal = golang_common.string_literal(f"{repo_url}/reporting")

    aasstringification_url_literal = golang_common.string_literal(
        f"{repo_url}/stringification"
    )

    blocks = [
        Stripped(
            """\
// Package jsonization de/serializes model instances to and from JSON.
//
// We can not use one-pass deserialization for JSON since the object
// properties do not have fixed order, and hence we can not read
// `modelType` property ahead of the remaining properties.
//
// To de-serialize, call one of the `*FromJsonable` functions.
//
// To serialize, call [ToJsonable] function.
package jsonization"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"
{I}"math"
{I}b64 "encoding/base64"
{I}aascommon {aascommon_url_literal}
{I}aasreporting {aasreporting_url_literal}
{I}aasstringification {aasstringification_url_literal}
{I}aastypes {aastypes_url_literal}
)"""
        ),
        Stripped("// region De-serialization"),
        Stripped(
            f"""\
// Represent an error during the de-serialization.
//
// Implements `error`.
type DeserializationError struct{{
{I}Path *aasreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newDeserializationError(message string) *DeserializationError {{
{I}return &DeserializationError{{
{II}Path: &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func (de *DeserializationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}de.PathString(),
{II}de.Message,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Render the path as a string.
func (de *DeserializationError) PathString() string {{
{I}return aasreporting.ToJSONPath(de.Path)
}}"""
        ),
        _generate_bool_from_jsonable(),
        _generate_int64_from_jsonable(),
        _generate_float64_from_jsonable(),
        _generate_string_from_jsonable(),
        _generate_bytes_from_jsonable(),
        _generate_parse_array(),
    ]  # type: List[Stripped]

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_parse_tuple_helper(arity))

    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_enumeration_from_jsonable(enumeration=our_type))
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            pass
        elif isinstance(our_type, intermediate.AbstractClass):
            blocks.append(_generate_class_from_jsonable(cls=our_type))
        elif isinstance(our_type, intermediate.ConcreteClass):
            blocks.append(_generate_class_from_jsonable(cls=our_type))

            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Jsonization/{our_type.name}_from_map.go"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The jsonization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue
            else:
                blocks.append(
                    _generate_concrete_class_from_map_without_dispatch(cls=our_type)
                )
        else:
            # noinspection PyTypeChecker
            assert_never(our_type)

    # NOTE (mristin):
    # We add all the dispatch mappings at the end as the functions might not have been
    # defined yet.
    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.AbstractClass):
            blocks.append(_generate_class_from_map(cls=cls))
        elif isinstance(cls, intermediate.ConcreteClass):
            if len(cls.concrete_descendants) > 0:
                blocks.append(_generate_class_from_map(cls=cls))
        else:
            # noinspection PyTypeChecker
            assert_never(cls)

    blocks.append(Stripped("// endregion"))

    blocks.append(Stripped("// region Serialization"))

    blocks.extend(
        [
            Stripped(
                f"""\
// Represent an error during the serialization.
//
// Implements `error`.
type SerializationError struct{{
{I}Path *aasreporting.Path
{I}Message string
}}"""
            ),
            Stripped(
                f"""\
func newSerializationError(message string) *SerializationError {{
{I}return &SerializationError{{
{II}Path: &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
            ),
            Stripped(
                f"""\
func (se *SerializationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}se.PathString(),
{II}se.Message,
{I})
}}"""
            ),
            Stripped(
                f"""\
// Render the path as a string.
func (se *SerializationError) PathString() string {{
{I}return aasreporting.ToGolangPath(se.Path)
}}"""
            ),
        ]
    )

    blocks.append(_generate_int64_to_jsonable())
    blocks.append(_generate_bytes_to_jsonable())
    blocks.append(_generate_serialize_array())

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.append(_generate_direct_to_jsonable())
        blocks.append(_generate_class_as_jsonable_interface())
        for enumeration in symbol_table.enumerations:
            blocks.append(_generate_enum_as_jsonable_interface(enumeration))
        for arity in tuple_arities:
            blocks.append(_generate_serialize_tuple_helper(arity))

    for enum in symbol_table.enumerations:
        blocks.append(_generate_enumeration_to_jsonable(enum))

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Jsonization/{cls.name}_to_map.go"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The jsonization snippet is missing "
                        f"for the implementation-specific "
                        f"class {cls.name}: {implementation_key}",
                    )
                )
                continue
        else:
            blocks.append(_generate_cls_to_map(cls))

    blocks.append(_generate_to_jsonable(symbol_table))

    blocks.append(Stripped("// endregion"))

    if len(errors) > 0:
        return None, errors

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
