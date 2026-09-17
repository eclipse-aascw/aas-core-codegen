"""Generate code for JSON de/serialization."""

import io
from typing import Tuple, Optional, List, Set, Union

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
    pointering as golang_pointering,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
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


def _generate_parse_optional() -> Stripped:
    """Generate the helper to turn a parsed value into a pointer."""
    return Stripped(
        f"""\
// Return a pointer to the `value`, or the `err`, if any.
//
// This function takes the *results* of a parse function instead of the parse
// function itself. Go binds all the results of a call to the whole parameter
// list of the enclosing call, so this single helper composes with every parse
// function, however many arguments that function takes -- including
// `parseOptional(parseTuple2(v, ...))`, which a parser-taking signature could
// not express, as the item parsers of a tuple vary both in number and in type.
func parseOptional[T any](value T, err error) (*T, error) {{
{I}if err != nil {{
{II}return nil, err
{I}}}
{I}return &value, nil
}}"""
    )


def _generate_not_a_map_error() -> Stripped:
    """Generate the helper to report a JSON-able which is no JSON object."""
    # NOTE (mristin):
    # Only the *error* is shared, not the cast which precedes it. Every instance goes
    # through that cast, and a helper performing it would have to hand the failure back
    # as an ``error``, so the caller would test a two-word interface where it now tests
    # a bool -- measurably slower on the happy path, for a function Go inlines anyhow.
    # A JSON null fails the cast just as a number does, so this is the place which
    # tells them apart.
    return Stripped(
        f"""\
// Report that `jsonable` is no JSON object.
func notAMapError(jsonable interface{{}}) error {{
{I}if jsonable == nil {{
{II}return newDeserializationError(
{III}"Expected a JSON object, but got null",
{II})
{I}}}

{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected a JSON object, but got %T",
{III}jsonable,
{II}),
{I})
}}"""
    )


def _generate_model_type_from_map() -> Stripped:
    """Generate the function to extract the model type discriminator from a map."""
    return Stripped(
        f"""\
// Extract the `modelType` property of `m` as a string, or return an error.
//
// This is the only place which knows how the model type is spelled on the wire.
// Both the dispatch on the model type and its check in a concrete class go
// through it.
func modelTypeFromMap(
{I}m map[string]interface{{}},
) (modelType string, err error) {{
{I}jsonable, ok := m["modelType"]
{I}if !ok {{
{II}err = newDeserializationError(
{III}"The required property modelType is missing",
{II})
{II}return
{I}}}

{I}modelType, err = stringFromJsonable(jsonable)
{I}if err != nil {{
{II}mustDeserializationError(err).prependName("modelType")
{I}}}
{I}return
}}"""
    )


def _generate_check_model_type() -> Stripped:
    """Generate the function to check the model type of a map against an expectation."""
    return Stripped(
        f"""\
// Check that `m` specifies the `expected` model type, or return an error.
func checkModelType(
{I}m map[string]interface{{}},
{I}expected string,
) (err error) {{
{I}var modelType string
{I}modelType, err = modelTypeFromMap(m)
{I}if err != nil {{
{II}return
{I}}}

{I}if modelType != expected {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected the model type '%s', but got %s",
{IIII}expected,
{IIII}modelType,
{III}),
{II}).prependName("modelType")
{I}}}
{I}return
}}"""
    )


def _generate_not_an_enum_text_error() -> Stripped:
    """Generate the helper to report a JSON-able which is no enumeration text."""
    return Stripped(
        f"""\
// Report that `jsonable` is no text of a literal of the enumeration `enumName`.
func notAnEnumTextError(
{I}jsonable interface{{}},
{I}enumName string,
) error {{
{I}if jsonable == nil {{
{II}return newDeserializationError(
{III}"Expected a string representation of " + enumName + ", but got null",
{II})
{I}}}

{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected a string representation of %s, but got %T",
{III}enumName,
{III}jsonable,
{II}),
{I})
}}"""
    )


def _generate_unexpected_enum_literal_error() -> Stripped:
    """Generate the helper to report a text which is no literal of an enumeration."""
    return Stripped(
        f"""\
// Report that `text` is no literal of the enumeration `enumName`.
func unexpectedEnumLiteralError(
{I}text string,
{I}enumName string,
) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected a string representation of %s, but got %v",
{III}enumName,
{III}text,
{II}),
{I})
}}"""
    )


def _generate_has_all_properties() -> Stripped:
    """Generate the helper to check the presence of properties in a map."""
    return Stripped(
        f"""\
// Check that `m` contains all the properties with the given `names`.
//
// The named unions are verified at the code generation time such that
// the required properties of the structurally dispatched implementers are
// pairwise disjoint. The presence of the properties thus suffices to tell
// the implementers apart, and their values need not be inspected.
func hasAllProperties(
{I}m map[string]interface{{}},
{I}names ...string,
) bool {{
{I}for _, name := range names {{
{II}if _, ok := m[name]; !ok {{
{III}return false
{II}}}
{I}}}
{I}return true
}}"""
    )


def _generate_union_from_map() -> Stripped:
    """Generate the generic helper to parse an implementer of a named union."""
    return Stripped(
        f"""\
// Parse `m` with `fromMap` and wrap the instance into a union with `newUnion`,
// or return an error.
func unionFromMap[I any, U any](
{I}m map[string]interface{{}},
{I}fromMap func(m map[string]interface{{}}) (I, error),
{I}newUnion func(that I) U,
) (result U, err error) {{
{I}var instance I
{I}instance, err = fromMap(m)
{I}if err != nil {{
{II}return
{I}}}
{I}result = newUnion(instance)
{I}return
}}"""
    )


def _generate_parse_array() -> Stripped:
    """Generate the generic helper to parse a JSON array item-by-item."""
    return Stripped(
        f"""\
// Parse `jsonable` as an array and parse every item with `parseItem`,
// or return an error.
func parseArray[T any](
{I}jsonable interface{{}},
{I}parseItem func(jsonable interface{{}}) (T, error),
) (result []T, err error) {{
{I}jsonableArray, ok := jsonable.([]interface{{}})
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an array, but got %T",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

{I}result = make([]T, len(jsonableArray))
{I}for i, itemJsonable := range jsonableArray {{
{II}var item T
{II}item, err = parseItem(itemJsonable)
{II}if err != nil {{
{III}mustDeserializationError(err).prependIndex(i)
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
{I}mustDeserializationError(err).prependIndex({i})
{I}return
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    item_fields_joined = ",\n".join(f"Item{i + 1}: item{i}" for i in range(arity))

    function_name = f"parseTuple{arity}"

    return Stripped(
        f"""\
// Parse `jsonable` as an array of exactly {arity} item(s) and parse them into
// a {tuple_type} with `parseItem0`, `parseItem1`, *etc.*,
// or return an error.
func {function_name}[{type_params_joined}](
{I}jsonable interface{{}},
{I}{indent_but_first_line(params_joined, I)},
) (result {tuple_type}, err error) {{
{I}jsonableArray, ok := jsonable.([]interface{{}})
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an array, but got %T",
{IIII}jsonable,
{III}),
{II})
{II}return
{I}}}

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

    enum_name_literal = golang_common.string_literal(enum_name)

    return Stripped(
        f"""\
// Parse `jsonable` as a literal of [aastypes.{enum_name}],
// or return an error.
func {function_name}(
{I}jsonable interface{{}},
) (result aastypes.{enum_name}, err error) {{
{I}text, ok := jsonable.(string)
{I}if !ok {{
{II}err = notAnEnumTextError(jsonable, {enum_name_literal})
{II}return
{I}}}

{I}result, ok = aasstringification.{enum_from_str}(text)
{I}if !ok {{
{II}err = unexpectedEnumLiteralError(text, {enum_name_literal})
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
{I}var modelType string
{I}modelType, err = modelTypeFromMap(m)
{I}if err != nil {{
{II}return
{I}}}

{I}switch modelType {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}

{I}return
}}"""
    )


def _generate_return_union_from_map(
    implementer: intermediate.ConcreteClass,
    named_union: intermediate.NamedUnion,
    indention: int,
) -> Stripped:
    """
    Generate the statement parsing the ``implementer`` and wrapping it in the union.

    We deliberately call the ``*FromMapWithoutDispatch`` function of the exact
    ``implementer`` instead of its public ``*FromJsonable``. The JSON-able has already
    been cast to a map, and the implementer has already been determined -- either by
    the model type, which the surrounding switch has just matched, or structurally.
    Going through ``*FromJsonable`` would re-do both, and, for an implementer with
    concrete descendants of its own, dispatch on the model type a second time.
    """
    from_map_name = golang_naming.private_function_name(
        Identifier(f"{implementer.name}_from_map_without_dispatch")
    )

    new_union_name = golang_naming.function_name(
        Identifier(f"new_{named_union.name}_from_{implementer.name}")
    )

    arguments = ["m", from_map_name, f"aastypes.{new_union_name}"]

    single_line = f"return unionFromMap({', '.join(arguments)})"
    if (
        indention * golang_common.TAB_WIDTH + len(single_line)
        <= golang_common.MAX_LINE_LENGTH
    ):
        return Stripped(single_line)

    arguments_joined = golang_common.join_arguments(arguments, indention + 1)

    return Stripped(
        f"""\
return unionFromMap(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
    )


def _generate_named_union_from_jsonable(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the de-serialization function for ``named_union``."""
    name = golang_naming.union_name(named_union.name)

    function_name = golang_naming.function_name(
        Identifier(f"{named_union.name}_from_jsonable")
    )

    with_model_type = []  # type: List[intermediate.ConcreteClass]
    without_model_type = []  # type: List[intermediate.ConcreteClass]

    for implementer in named_union.implementers:
        if implementer.serialization.with_model_type:
            with_model_type.append(implementer)
        else:
            without_model_type.append(implementer)

    blocks = [
        Stripped(
            f"""\
m, ok := jsonable.(map[string]interface{{}})
if !ok {{
{I}err = notAMapError(jsonable)
{I}return
}}"""
        )
    ]  # type: List[Stripped]

    if len(with_model_type) > 0:
        # NOTE (mristin):
        # The model type is optional here. An implementer which does not specify it is
        # dispatched structurally below, so a missing ``modelType`` is not an error.
        case_blocks = []  # type: List[Stripped]
        for implementer in with_model_type:
            model_type_literal = golang_common.string_literal(
                naming.json_model_type(implementer.name)
            )

            statement = _generate_return_union_from_map(
                implementer=implementer,
                named_union=named_union,
                indention=3,
            )

            case_blocks.append(
                Stripped(
                    f"""\
case {model_type_literal}:
{I}{indent_but_first_line(statement, I)}"""
                )
            )

        case_blocks.append(
            Stripped(
                f"""\
default:
{I}err = newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected model type for the union {name}: %s",
{III}modelType,
{II}),
{I})
{I}return"""
            )
        )

        case_blocks_joined = "\n".join(case_blocks)

        blocks.append(
            Stripped(
                f"""\
if _, found := m["modelType"]; found {{
{I}var modelType string
{I}modelType, err = modelTypeFromMap(m)
{I}if err != nil {{
{II}return
{I}}}

{I}switch modelType {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
}}"""
            )
        )

    for implementer in without_model_type:
        required_props = [
            prop
            for prop in implementer.properties
            if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        ]
        assert len(required_props) > 0, (
            f"Expected at least one required property for the structurally "
            f"dispatched implementer {implementer.name!r} of "
            f"the union {named_union.name!r}; this should have already been "
            f"verified in the intermediate stage."
        )

        arguments = ["m"] + [
            golang_common.string_literal(prop.json_name) for prop in required_props
        ]

        condition: Stripped

        single_line = f"if hasAllProperties({', '.join(arguments)})"
        if golang_common.TAB_WIDTH + len(single_line) <= golang_common.MAX_LINE_LENGTH:
            condition = Stripped(single_line)
        else:
            arguments_joined = golang_common.join_arguments(arguments, 2)

            condition = Stripped(
                f"""\
if hasAllProperties(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
            )

        statement = _generate_return_union_from_map(
            implementer=implementer,
            named_union=named_union,
            indention=2,
        )

        blocks.append(
            Stripped(
                f"""\
{condition} {{
{I}{indent_but_first_line(statement, I)}
}}"""
            )
        )

    blocks.append(
        Stripped(
            f"""\
err = newDeserializationError(
{I}"Could not determine the concrete type of the union {name}: " +
{II}"none of its implementers matched",
)
return"""
        )
    )

    body = Stripped("\n\n".join(blocks))

    return Stripped(
        f"""\
// Parse `jsonable` as an instance of [aastypes.{name}],
// or return an error.
func {function_name}(
{I}jsonable interface{{}},
) (
{I}result *aastypes.{name},
{I}err error,
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_class_from_jsonable(cls: intermediate.ClassUnion) -> Stripped:
    """Generate the de-serialization function for a class from a JSON-able."""
    function_name = golang_naming.function_name(Identifier(f"{cls.name}_from_jsonable"))

    interface_name = golang_naming.interface_name(cls.name)

    blocks = [
        Stripped(
            f"""\
m, ok := jsonable.(map[string]interface{{}})
if !ok {{
{I}err = notAMapError(jsonable)
{I}return
}}"""
        )
    ]  # type: List[Stripped]

    from_map_name: str

    if len(cls.concrete_descendants) == 0:
        assert not isinstance(cls, intermediate.AbstractClass), (
            "We can not parse abstract classes without any concrete descendants "
            "as we do not know the concrete structure of the map."
        )

        from_map_name = golang_naming.private_function_name(
            Identifier(f"{cls.name}_from_map_without_dispatch")
        )

        # NOTE (mristin):
        # This is the only path into the class which does not dispatch on the model
        # type, so this is where the model type has to be checked. On the dispatched
        # path, the switch of the dispatching function has already matched it, see
        # :py:func:`_generate_class_from_map`.
        if cls.serialization.with_model_type:
            model_type_literal = golang_common.string_literal(
                naming.json_model_type(cls.name)
            )

            blocks.append(
                Stripped(
                    f"""\
err = checkModelType(m, {model_type_literal})
if err != nil {{
{I}return
}}"""
                )
            )
    else:
        from_map_name = golang_naming.private_function_name(
            Identifier(f"{cls.name}_from_map")
        )

    blocks.append(Stripped(f"return {from_map_name}(m)"))

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

        elif isinstance(our_type, intermediate.NamedUnion):
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


#: Number of tabs the body of a ``case`` of the property switch is indented by, counted
#: from the beginning of the line -- one for the function body, one for the ``for``
#: loop and one for the ``case`` itself
_CASE_BODY_INDENTION = 3


def _generate_deserialization_switch_statement(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the switch statement for de-serialization of the properties.

    This statement is expected to be run in a ``for k, v := range m`` loop. We switch
    on ``k`` and the value of the property is given as ``v``. The ``jsonable`` is
    expected to be of type ``map[string]interface{}``.

    Every case is a single assignment to the corresponding ``the*`` variable. The error
    is deliberately *not* checked in the case, but once after the switch, where ``k``
    is at hand -- ``k`` is exactly the JSON name of the property, so the path segment
    needs no literal of its own, and the check needs no copy of its own.

    The resulting struct we parse into is ``result``, a pointer to the struct
    corresponding to ``cls``. Whenever we encounter a required property, we have to set
    the corresponding boolean ``found*`` to ``true``.

    This function was originally part of
    ``_generate_concrete_class_from_map_without_dispatch``, but we refactored it out
    since it was too much to read. Best if your read both functions in two vertical
    editor panes.

    The model type, if the serialization requires one, is checked by the caller before
    the loop, so that a wrong model type is reported without de-serializing any of
    the properties first. The case for it is therefore empty, and only keeps the model
    type from being reported as an unexpected property.
    """
    case_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        json_prop_literal = golang_common.string_literal(prop.json_name)

        function: str
        arguments: List[str]

        if isinstance(
            type_anno,
            (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
        ):
            function = _determine_parse_function_for_atomic_value(type_anno)
            arguments = ["v"]

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We expect only lists of atomic types "
                f"at the moment, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            function = "parseArray"
            arguments = [
                "v",
                _determine_parse_function_for_atomic_value(type_anno.items),
            ]

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            function = f"parseTuple{len(type_anno.items)}"
            arguments = ["v"]

            for item_type_anno in type_anno.items:
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"NOTE (mristin): We expect only atomic items in a tuple "
                    f"at the moment, but got {item_type_anno} in {type_anno}. "
                    f"This should have already been verified in "
                    f"intermediate._translate._verify_only_simple_type_patterns."
                )

                arguments.append(
                    _determine_parse_function_for_atomic_value(item_type_anno)
                )

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        # NOTE (mristin):
        # An optional value which Go can not represent as nil on its own is modeled as
        # a pointer. ``parseOptional`` takes the results of the parse function and
        # gives us back the pointer, so that the case stays a single statement whatever
        # the property is -- a scalar, an enumeration or a tuple.
        prefix = f"{prop_var}, err = "

        pointer = golang_pointering.is_pointer_type(prop.type_annotation)

        call = f"{function}({', '.join(arguments)})"

        case_body: Stripped

        single_line = f"{prefix}parseOptional({call})" if pointer else f"{prefix}{call}"
        if (
            _CASE_BODY_INDENTION * golang_common.TAB_WIDTH + len(single_line)
            <= golang_common.MAX_LINE_LENGTH
        ):
            case_body = Stripped(single_line)
        elif pointer:
            # NOTE (mristin):
            # The call itself goes one tab deeper, as it is now an argument
            # to ``parseOptional``, and might or might not fit on a line of its own.
            inner_indention = _CASE_BODY_INDENTION + 1

            inner: Stripped
            if (
                inner_indention * golang_common.TAB_WIDTH + len(call)
                <= golang_common.MAX_LINE_LENGTH
            ):
                inner = Stripped(call)
            else:
                arguments_joined = golang_common.join_arguments(
                    arguments, inner_indention + 1
                )

                inner = Stripped(
                    f"""\
{function}(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
                )

            case_body = Stripped(
                f"""\
{prefix}parseOptional(
{I}{indent_but_first_line(inner, I)},
)"""
            )
        else:
            arguments_joined = golang_common.join_arguments(
                arguments, _CASE_BODY_INDENTION + 1
            )

            case_body = Stripped(
                f"""\
{prefix}{function}(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
            )

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
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
        case_blocks.append(
            Stripped(
                f"""\
case "modelType":
{I}// The model type has already been checked before the loop."""
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

    The model type is *not* checked here. Either a dispatch function has matched it in
    its switch, or ``*FromJsonable`` has checked it before calling us -- see
    :py:func:`_generate_class_from_map` and :py:func:`_generate_class_from_jsonable`.
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

    # region Switch on property name

    switch_statement = _generate_deserialization_switch_statement(cls=cls)

    # endregion

    # NOTE (mristin):
    # ``v`` is only referenced in the case branches which actually parse a property.
    # If there are none, ``v`` would be declared, but never used, which Go rejects at
    # compile time. The same goes for the check of the error, which no case but those
    # can set -- the default case returns on its own.
    if len(cls.properties) > 0:
        blocks.append(
            Stripped(
                f"""\
for k, v := range m {{
{I}{indent_but_first_line(switch_statement, I)}

{I}if err != nil {{
{II}mustDeserializationError(err).prependName(k)
{II}return
{I}}}
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
{II}result[i], err = serializeItem(item)
{II}if err != nil {{
{III}mustSerializationError(err).prependIndex(i)
{III}return
{II}}}
{I}}}
{I}return
}}"""
    )


def _generate_direct_to_jsonable() -> Stripped:
    """
    Generate the generic function to forward a value as a JSON-able as-is.

    ``serializeArray`` (see :py:func:`_generate_serialize_array`) and
    ``serializeTupleN`` (see :py:func:`_generate_serialize_tuple_helper`)
    accept a plain ``func(item T) (interface{}, error)`` per item, so an
    item whose serialization already resolves to a single named
    function of ours with exactly that shape can be passed on directly, with
    no wrapping closure -- see :py:func:`_item_serializer_function`.

    A ``bool``/``float64``/``string`` item needs no conversion at all in
    Go's JSON representation, so this generic identity-like function stands
    in for those directly, instead of a closure repeated at every such item.
    """
    return Stripped(
        f"""\
// Forward `item` as a JSON-able value, unconverted.
func directToJsonable[T any](item T) (interface{{}}, error) {{
{I}return item, nil
}}"""
    )


def _generate_class_as_jsonable_interface() -> Stripped:
    """Generate the wrapper so a class item is a bare function reference."""
    return Stripped(
        f"""\
// Serialize `that` to a JSON-able value, or return an error.
//
// `ToJsonable` takes an `aastypes.IClass`, but a list or a tuple item's own
// (more specific) interface type, e.g., `aastypes.ISomeItem`, can not be
// unified with that when passing `ToJsonable` itself as a
// `func(item T) (interface{{}}, error)` value -- Go function values are
// invariant in their parameter type (no contravariance, unlike, say, a C#
// delegate). Making this wrapper itself generic (instead of fixing its
// parameter to `aastypes.IClass`) lets the very same one be passed on bare,
// uninstantiated, for every class-typed item regardless of its
// concrete interface: Go infers both the item's type and this
// wrapper's own type parameter together from the context of the
// `serializeArray`/`serializeTupleN` call.
func classAsJsonableInterface[T aastypes.IClass](that T) (interface{{}}, error) {{
{I}return ToJsonable(that)
}}"""
    )


def _generate_enum_as_jsonable_interface(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the wrapper so an enum item is a bare function reference."""
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
// error)` is expected, e.g. as an item serializer in a list or a tuple.
// This wrapper exists solely to have the right signature.
func {function_name}(that aastypes.{enum_name}) (interface{{}}, error) {{
{I}return {to_jsonable}(that)
}}"""
    )


def _generate_union_as_jsonable_interface() -> Stripped:
    """
    Generate the wrapper so a named-union item is a bare function reference.

    ``ToJsonable`` takes an ``aastypes.IClass``, which a named union is
    deliberately not, but every named union exposes its underlying instance
    through ``Underlying`` -- constraining this wrapper's type parameter to
    that single method (instead of a fixed union type) lets the very same
    one be passed on bare, uninstantiated, for every union-typed item,
    mirroring :py:func:`_generate_class_as_jsonable_interface`.
    """
    return Stripped(
        f"""\
// Constrain a generic type to a named union, giving access to its
// underlying instance for serialization.
type namedUnion interface {{
{I}Underlying() aastypes.IClass
}}

// Serialize `that` union to a JSON-able value, or return an error.
func unionAsJsonableInterface[T namedUnion](that T) (interface{{}}, error) {{
{I}return ToJsonable(that.Underlying())
}}"""
    )


def _item_serializer_function(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """
    Determine the function reference to serialize an item of a list or of a tuple.

    Unlike a property, which is serialized by a statement written out in place,
    an item is serialized by a function passed on as a value to
    ``serializeArray``/``serializeTupleN``. Hence the serialization of every item
    type has to resolve to a single named function with the uniform signature
    ``func(item T) (interface{}, error)``, which is what the wrappers
    ``directToJsonable``, ``classAsJsonableInterface``, ``unionAsJsonableInterface``
    and ``{enumeration}AsJsonableInterface`` provide.

    ``directToJsonable``, ``classAsJsonableInterface`` and ``unionAsJsonableInterface``
    are themselves generic, so -- exactly as for ``asInstanceTupleItemWriter`` in XML
    de/serialization (see :py:func:`_generate_as_instance_tuple_item_writer`
    in ``_generate_xmlization.py``) -- we have to instantiate them
    explicitly at every call site with the item's own Go type. Go can not
    infer the type parameter for a generic function passed on as a bare,
    uncalled value without ``go1.21``, and this project intentionally
    targets ``go1.18``.

    Keep this in sync with :py:func:`_determine_item_serializer_wrappers`, which
    decides which of the wrappers have to be generated at all.
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
    elif isinstance(our_type, intermediate.NamedUnion):
        item_type = golang_common.generate_type(
            type_annotation=type_annotation, types_package=Identifier("aastypes")
        )
        return Stripped(f"unionAsJsonableInterface[{item_type}]")
    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        raise AssertionError(
            f"Unexpected {our_type=}: a constrained primitive should have "
            f"already been handled above through ``primitive_type``"
        )
    else:
        assert_never(our_type)


class _ItemSerializerWrappers:
    """
    Capture which item serializer wrappers the generated code needs.

    Companion to :py:func:`_item_serializer_function`, which picks the reference
    for a single item -- the two have to be kept in sync.
    """

    def __init__(self) -> None:
        """Initialize with no wrapper needed at all."""
        self.direct = False
        self.instance = False
        self.enumerations = []  # type: List[intermediate.Enumeration]
        self.union = False


def _determine_item_serializer_wrappers(
    symbol_table: intermediate.SymbolTable,
) -> _ItemSerializerWrappers:
    """Determine the wrappers needed to serialize the list and the tuple items."""
    result = _ItemSerializerWrappers()

    enumeration_names = set()  # type: Set[Identifier]

    item_type_annotations = []  # type: List[intermediate.TypeAnnotationUnion]
    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            # NOTE (mristin):
            # The serialization of an implementation-specific class comes from
            # a snippet, so we do not know and do not generate anything for it.
            continue

        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(type_anno, intermediate.ListTypeAnnotation):
                item_type_annotations.append(type_anno.items)
            elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                item_type_annotations.extend(type_anno.items)
            else:
                pass

    for item_type_anno in item_type_annotations:
        primitive_type = intermediate.try_primitive_type(item_type_anno)

        if primitive_type is not None:
            if primitive_type not in (
                intermediate.PrimitiveType.INT,
                intermediate.PrimitiveType.BYTEARRAY,
            ):
                # NOTE (mristin):
                # ``int64ToJsonable`` and ``bytesToJsonable`` are generated
                # unconditionally, and already have the expected signature.
                result.direct = True

            continue

        assert isinstance(item_type_anno, intermediate.OurTypeAnnotation)
        our_type = item_type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            enumeration_names.add(our_type.name)
        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            result.instance = True
        elif isinstance(our_type, intermediate.NamedUnion):
            result.union = True
        else:
            raise AssertionError(
                f"Unexpected {our_type=}: a constrained primitive should have "
                f"already been handled above through ``primitive_type``"
            )

    # NOTE (mristin):
    # We go over the symbol table instead of over the collected items so that
    # the wrappers come out in the order of the definitions, and not in the order
    # in which the properties happen to use them.
    result.enumerations = [
        enumeration
        for enumeration in symbol_table.enumerations
        if enumeration.name in enumeration_names
    ]

    return result


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
result[{i}], err = serializeItem{i}(that.Item{i + 1})
if err != nil {{
{I}mustSerializationError(err).prependIndex({i})
{I}return
}}"""
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


def _determine_serialization_of_atomic_value(
    access_expression: str, type_annotation: TypeAnnotationExceptList
) -> Tuple[Optional[Stripped], Stripped]:
    """
    Determine how to serialize the ``access_expression``.

    The ``access_expression`` is for example a name or a property access.
    The caller is expected to have already generated the code which checks that
    ``access_expression`` is not nil.

    Return (function to call, the expression to pass to it as the argument). If
    the function is None, the expression already *is* the JSON-able value, so it
    needs neither a call nor an error check.
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

        dereferenced = (
            Stripped(f"*({access_expression})")
            if optional
            else Stripped(access_expression)
        )

        if primitive_type is intermediate.PrimitiveType.INT:
            return Stripped("int64ToJsonable"), dereferenced

        elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            # NOTE (mristin):
            # A byte array is represented as a Golang slice, which is nilable on
            # its own, so an optional one is no pointer and needs no dereferencing.
            return Stripped("bytesToJsonable"), Stripped(access_expression)

        elif isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type, intermediate.Enumeration
        ):
            enum_to_jsonable = golang_naming.function_name(
                Identifier(f"{type_anno.our_type.name}_to_jsonable")
            )

            return Stripped(enum_to_jsonable), dereferenced

        else:
            return None, (
                Stripped(f"*{access_expression}")
                if optional
                else Stripped(access_expression)
            )

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
            return Stripped("ToJsonable"), Stripped(access_expression)

        elif isinstance(our_type, intermediate.NamedUnion):
            return Stripped("ToJsonable"), Stripped(f"{access_expression}.Underlying()")

        else:
            # noinspection PyTypeChecker
            assert_never(our_type)
    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)

    raise AssertionError("Should not have gotten here")


def _generate_cls_to_map(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the function to serialize class to a JSON-able map.

    The generated function will perform no dispatching.
    """
    blocks = [Stripped("result = make(map[string]interface{})")]  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

        getter_name = golang_naming.getter_name(prop.name)

        access_expression = f"that.{getter_name}()"

        prop_literal = golang_common.string_literal(
            f"{golang_naming.property_name(prop.name)}()"
        )

        target = f"result[{golang_common.string_literal(prop.json_name)}]"

        # NOTE (mristin):
        # The statement lives one tab deep in the function body, and one tab deeper
        # yet if it is wrapped in the nil-check of an optional property.
        indention = 2 if optional else 1

        function = None  # type: Optional[str]
        arguments = None  # type: Optional[List[str]]
        block: Stripped

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "(mristin): We currently generate only the code to serialize lists of "
                "atomic values. If you need this feature, please contact "
                "the developers."
            )

            function = "serializeArray"
            arguments = [
                access_expression,
                _item_serializer_function(type_anno.items),
            ]
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_serializers = []  # type: List[str]

            for item_type_anno in type_anno.items:
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"NOTE (mristin): We expect only atomic items in a tuple "
                    f"at the moment, but got {item_type_anno} in {type_anno}. "
                    f"This should have already been verified in "
                    f"intermediate._translate._verify_only_simple_type_patterns."
                )

                item_serializers.append(_item_serializer_function(item_type_anno))

            function = f"serializeTuple{len(type_anno.items)}"

            # NOTE (mristin):
            # A tuple is represented as a Golang struct, which is not nilable, so
            # an optional tuple is modeled as a pointer and has to be dereferenced.
            arguments = [
                f"*({access_expression})" if optional else access_expression
            ] + item_serializers
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
            function, argument_expression = (
                _determine_serialization_of_atomic_value(
                    access_expression=access_expression,
                    type_annotation=prop.type_annotation
                )
            )
            # fmt: on

            arguments = [argument_expression]

        if function is None:
            assert arguments is not None and len(arguments) == 1
            block = Stripped(f"{target} = {arguments[0]}")
        else:
            assert arguments is not None

            statement: Stripped

            single_line = f"{target}, err = {function}({', '.join(arguments)})"
            if (
                indention * golang_common.TAB_WIDTH + len(single_line)
                <= golang_common.MAX_LINE_LENGTH
            ):
                statement = Stripped(single_line)
            else:
                arguments_joined = golang_common.join_arguments(
                    arguments, indention + 1
                )

                statement = Stripped(
                    f"""\
{target}, err = {function}(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
                )

            block = Stripped(
                f"""\
{statement}
if err != nil {{
{I}mustSerializationError(err).prependName({prop_literal})
{I}return
}}"""
            )

        if optional:
            block = Stripped(
                f"""\
if {access_expression} != nil {{
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
        Stripped(
            f"""\
// Prepend the `name` segment to the path, and return the error back
// for chaining.
func (de *DeserializationError) prependName(
{I}name string,
) *DeserializationError {{
{I}de.Path.PrependName(
{II}&aasreporting.NameSegment{{Name: name}},
{I})
{I}return de
}}"""
        ),
        Stripped(
            f"""\
// Prepend the `index` segment to the path, and return the error back
// for chaining.
func (de *DeserializationError) prependIndex(
{I}index int,
) *DeserializationError {{
{I}de.Path.PrependIndex(
{II}&aasreporting.IndexSegment{{Index: index}},
{I})
{I}return de
}}"""
        ),
        Stripped(
            f"""\
// Cast `err` to a de-serialization error, or panic.
//
// Every error which originates in this package is
// a [DeserializationError], so the cast can only fail if a de-serialization
// snippet specific to an implementation returned a foreign error.
func mustDeserializationError(err error) *DeserializationError {{
{I}deseriaErr, ok := err.(*DeserializationError)
{I}if !ok {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Expected a *DeserializationError, but got %T: %v",
{IIII}err,
{IIII}err,
{III}),
{II})
{I}}}
{I}return deseriaErr
}}"""
        ),
        _generate_bool_from_jsonable(),
        _generate_int64_from_jsonable(),
        _generate_float64_from_jsonable(),
        _generate_string_from_jsonable(),
        _generate_bytes_from_jsonable(),
        _generate_parse_optional(),
        _generate_not_a_map_error(),
        _generate_model_type_from_map(),
        _generate_check_model_type(),
        _generate_parse_array(),
    ]  # type: List[Stripped]

    if len(symbol_table.enumerations) > 0:
        blocks.append(_generate_not_an_enum_text_error())
        blocks.append(_generate_unexpected_enum_literal_error())

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_has_all_properties())
        blocks.append(_generate_union_from_map())

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
        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_named_union_from_jsonable(named_union=our_type))
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
            Stripped(
                f"""\
// Prepend the `name` segment to the path, and return the error back
// for chaining.
func (se *SerializationError) prependName(
{I}name string,
) *SerializationError {{
{I}se.Path.PrependName(
{II}&aasreporting.NameSegment{{Name: name}},
{I})
{I}return se
}}"""
            ),
            Stripped(
                f"""\
// Prepend the `index` segment to the path, and return the error back
// for chaining.
func (se *SerializationError) prependIndex(
{I}index int,
) *SerializationError {{
{I}se.Path.PrependIndex(
{II}&aasreporting.IndexSegment{{Index: index}},
{I})
{I}return se
}}"""
            ),
            Stripped(
                f"""\
// Cast `err` to a serialization error, or panic.
//
// Every error which originates in this package is a [SerializationError],
// so the cast can only fail if a serialization snippet specific to
// an implementation returned a foreign error.
func mustSerializationError(err error) *SerializationError {{
{I}seriaErr, ok := err.(*SerializationError)
{I}if !ok {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"Expected a *SerializationError, but got %T: %v",
{IIII}err,
{IIII}err,
{III}),
{II})
{I}}}
{I}return seriaErr
}}"""
            ),
        ]
    )

    blocks.append(_generate_int64_to_jsonable())
    blocks.append(_generate_bytes_to_jsonable())
    blocks.append(_generate_serialize_array())

    item_serializer_wrappers = _determine_item_serializer_wrappers(symbol_table)

    if item_serializer_wrappers.direct:
        blocks.append(_generate_direct_to_jsonable())

    if item_serializer_wrappers.instance:
        blocks.append(_generate_class_as_jsonable_interface())

    for enumeration in item_serializer_wrappers.enumerations:
        blocks.append(_generate_enum_as_jsonable_interface(enumeration))

    if item_serializer_wrappers.union:
        blocks.append(_generate_union_as_jsonable_interface())

    for arity in intermediate.tuple_arities(symbol_table):
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

            blocks.append(Stripped(implementation))
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
