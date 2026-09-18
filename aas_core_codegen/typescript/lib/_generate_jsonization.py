"""Generate code for JSON de/serialization."""

import io
import textwrap
from typing import Dict, List, Optional, Sequence, Set, Tuple

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.typescript import (
    common as typescript_common,
    naming as typescript_naming,
    description as typescript_description,
)
from aas_core_codegen.typescript.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


# region De-serialization


def _generate_parse_array() -> Stripped:
    """
    Generate the generic helper to parse a JSON array item-by-item.

    The iterable is checked for here rather than at the point of the call, so that
    a list-valued property is de-serialized by a single call just as an atomic one
    is; see :py:func:`_generate_parse_call_for_property`.
    """
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as an array, and every one of its items with `parseItem`.
 *
 * @param jsonable - to be parsed item-by-item
 * @param parseItem - to parse a single item of `jsonable`
 * @returns parsed items, or an error
 * @typeParam T - type of a single parsed item
 */
function parseArray<T>(
{I}jsonable: JsonValue,
{I}parseItem: (
{II}jsonableItem: JsonValue
{I}) => AasCommon.Either<T, DeserializationError>
): AasCommon.Either<Array<T>, DeserializationError> {{
{I}const iterableError = checkIsIterable(jsonable);
{I}if (iterableError !== null) {{
{II}return new AasCommon.Either<Array<T>, DeserializationError>(
{III}null,
{III}iterableError
{II});
{I}}}

{I}const iterable = <Iterable<JsonValue>>jsonable;

{I}const items = new Array<T>();
{I}let i = 0;
{I}for (const jsonableItem of iterable) {{
{II}const itemOrError = parseItem(jsonableItem);
{II}if (itemOrError.error !== null) {{
{III}itemOrError.error.path.prepend(new IndexSegment(iterable, i));
{III}return new AasCommon.Either<Array<T>, DeserializationError>(
{IIII}null,
{IIII}itemOrError.error
{III});
{II}}}
{II}items.push(itemOrError.mustValue());
{II}i++;
{I}}}
{I}return new AasCommon.Either<Array<T>, DeserializationError>(items, null);
}}"""
    )


def _generate_extract_model_type() -> Stripped:
    """
    Generate the generic helper to read the ``modelType`` property of an object.

    This is the single place which knows how the discriminator is spelled and typed
    on the wire. The dispatching functions and ``checkModelType`` share it.
    """
    return Stripped(
        f"""\
/**
 * Extract the `modelType` property of `jsonObject`.
 *
 * @param jsonObject - to be inspected
 * @returns the model type, or an error
 */
function extractModelType(
{I}jsonObject: JsonObject
): AasCommon.Either<string, DeserializationError> {{
{I}const modelType = jsonObject["modelType"];
{I}if (modelType === undefined) {{
{II}return newDeserializationError<string>(
{III}"The required property 'modelType' is missing"
{II});
{I}}}
{I}if (typeof modelType !== "string") {{
{II}return newDeserializationError<string>(
{III}`Expected the property modelType to be a string, ` +
{III}`but got: ${{typeof modelType}}`
{II});
{I}}}

{I}return new AasCommon.Either<string, DeserializationError>(modelType, null);
}}"""
    )


def _generate_check_model_type() -> Stripped:
    """
    Generate the generic helper to verify the ``modelType`` property of an object.

    The helper reads the property itself instead of taking it already parsed, so
    that it can be called in front of the property loop: a wrong model type is
    then reported without de-serializing any of the properties first.
    """
    return Stripped(
        f"""\
/**
 * Check that the `modelType` property of `jsonObject` is `expected`.
 *
 * @param jsonObject - to be inspected
 * @param expected - expected model type
 * @returns error, if any
 */
function checkModelType(
{I}jsonObject: JsonObject,
{I}expected: string
): DeserializationError | null {{
{I}const modelTypeOrError = extractModelType(jsonObject);
{I}if (modelTypeOrError.error !== null) {{
{II}return modelTypeOrError.error;
{I}}}

{I}const modelType = modelTypeOrError.mustValue();
{I}if (modelType !== expected) {{
{II}return new DeserializationError(
{III}`Expected model type '${{expected}}', ` +
{III}`but got: ${{modelType}}`
{II});
{I}}}

{I}return null;
}}"""
    )


def _generate_check_is_json_object() -> Stripped:
    """Generate the generic helper to check that a JSON-able is a JSON object."""
    return Stripped(
        f"""\
/**
 * Check that `jsonable` looks like a JSON object, without parsing it.
 *
 * @param jsonable - to be checked
 * @returns error, if any
 */
function checkIsJsonObject(jsonable: JsonValue): DeserializationError | null {{
{I}if (jsonable === null) {{
{II}return new DeserializationError(
{III}"Expected a JSON object, but got null"
{II});
{I}}}
{I}if (Array.isArray(jsonable)) {{
{II}return new DeserializationError(
{III}"Expected a JSON object, but got a JSON array"
{II});
{I}}}
{I}if (typeof jsonable !== "object") {{
{II}return new DeserializationError(
{III}`Expected a JSON object, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}return null;
}}"""
    )


def _generate_check_is_iterable() -> Stripped:
    """Generate the generic helper to check that a JSON-able is an iterable."""
    return Stripped(
        f"""\
/**
 * Check that `jsonable` looks like an iterable which can be parsed
 * item-by-item, without consuming it.
 *
 * @param jsonable - to be checked
 * @returns error, if any
 */
function checkIsIterable(jsonable: JsonValue): DeserializationError | null {{
{I}if (jsonable === null) {{
{II}return new DeserializationError(
{III}"Expected an iterable, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "object") {{
{II}return new DeserializationError(
{III}`Expected an iterable, but got: ${{typeof jsonable}}`
{II});
{I}}}
{I}if (typeof jsonable[Symbol.iterator] !== "function") {{
{II}return new DeserializationError(
{III}"Expected an iterable with iterator function, " +
{IIII}`but got iterator of type: ${{typeof jsonable[Symbol.iterator]}}`
{II});
{I}}}

{I}return null;
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_parse_tuple_helper(arity: int) -> Stripped:
    """
    Generate the generic helper to parse a JSON array into a tuple of `arity`.

    Every atomic value parser (see :py:func:`_parse_function_for_atomic_value`)
    already has the uniform signature ``(jsonable: JsonValue) =>
    AasCommon.Either<T, DeserializationError>`` -- the very same shape
    :py:func:`_generate_parse_array` expects for a list item -- so a tuple
    item's parser can be passed on to the generated function as a bare
    reference, with no adapter or closure needed.

    Just as in :py:func:`_generate_parse_array`, the iterable is checked for here
    rather than at the point of the call.

    We consume the iterable through its iterator protocol instead of
    materializing it into an ``Array`` first, so that we never pay for a copy
    we do not need. The common case -- a JSON-parsed array -- already exposes
    ``.length``, which we use for an immediate, cheap fail-fast arity check
    before parsing a single item; a non-array iterable is simply iterated
    item-by-item, and a too-few/too-many mismatch is caught as it is
    encountered.
    """
    type_params = [f"T{i}" for i in range(arity)]
    type_params_joined = ", ".join(type_params)
    tuple_type = f"[{', '.join(type_params)}]"

    param_docs = "\n".join(
        f" * @param parseItem{i} - to parse the item at index {i} of `jsonable`"
        for i in range(arity)
    )
    type_param_docs = "\n".join(
        f" * @typeParam {type_params[i]} - type of the item at index {i}"
        for i in range(arity)
    )

    params_joined = ",\n".join(
        f"""\
parseItem{i}: (
{I}jsonableItem: JsonValue
) => AasCommon.Either<{type_params[i]}, DeserializationError>"""
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
const next{i} = iterator.next();
if (next{i}.done) {{
{I}return newDeserializationError<{tuple_type}>(
{II}`Expected exactly {arity} item(s) in the array, ` +
{III}`but got only {i} item(s)`
{I});
}}
const item{i}OrError = parseItem{i}(next{i}.value);
if (item{i}OrError.error !== null) {{
{I}item{i}OrError.error.path.prepend(new IndexSegment(iterable, {i}));
{I}return new AasCommon.Either<{tuple_type}, DeserializationError>(
{II}null,
{II}item{i}OrError.error
{I});
}}"""
            )
        )
    item_blocks_joined = "\n\n".join(item_blocks)

    values_joined = ",\n".join(f"item{i}OrError.mustValue()" for i in range(arity))

    function_name = f"parseTuple{arity}"

    return Stripped(
        f"""\
/**
 * Parse `jsonable` into a tuple of {arity} item(s) by calling `parseItem0`,
 * `parseItem1`, *etc.* on the correspondingly positioned item.
 *
 * @param jsonable - expected to be an array of exactly {arity} item(s)
{param_docs}
 * @returns parsed tuple, or an error
{type_param_docs}
 */
function {function_name}<{type_params_joined}>(
{I}jsonable: JsonValue,
{I}{indent_but_first_line(params_joined, I)}
): AasCommon.Either<{tuple_type}, DeserializationError> {{
{I}const iterableError = checkIsIterable(jsonable);
{I}if (iterableError !== null) {{
{II}return new AasCommon.Either<{tuple_type}, DeserializationError>(
{III}null,
{III}iterableError
{II});
{I}}}

{I}const iterable = <Iterable<JsonValue>>jsonable;

{I}if (Array.isArray(iterable) && iterable.length !== {arity}) {{
{II}return newDeserializationError<{tuple_type}>(
{III}`Expected exactly {arity} item(s) in the array, ` +
{IIII}`but got: ${{iterable.length}}`
{II});
{I}}}

{I}const iterator = iterable[Symbol.iterator]();

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}const nextExtra = iterator.next();
{I}if (!nextExtra.done) {{
{II}return newDeserializationError<{tuple_type}>(
{III}`Expected exactly {arity} item(s) in the array, but got more`
{II});
{I}}}

{I}return new AasCommon.Either<{tuple_type}, DeserializationError>(
{II}[
{III}{indent_but_first_line(values_joined, III)}
{II}],
{II}null
{I});
}}"""
    )


def _generate_bool_from_jsonable() -> Stripped:
    """Generate the function to decode a ``bool`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a boolean.
 *
 * @param jsonable - to be parsed
 * @returns parsed boolean value, or an error
 */
function booleanFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<boolean, DeserializationError> {{
{I}// `typeof` seems to be optimized these days, so we use it instead of
{I}// literal comparison, see:
{I}// https://stackoverflow.com/questions/61786250/is-typeof-faster-than-literal-comparison

{I}if (jsonable === null) {{
{II}return newDeserializationError<boolean>(
{III}"Expected a boolean, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "boolean") {{
{II}return newDeserializationError<boolean>(
{III}`Expected a boolean, but got ${{typeof jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<boolean, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_int_from_jsonable() -> Stripped:
    """Generate the function to decode an ``int`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as an integer.
 *
 * @param jsonable - to be parsed
 * @returns parsed integer value, or an error
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function integerFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<number, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<number>(
{III}"Expected an integer number, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "number") {{
{II}return newDeserializationError<number>(
{III}`Expected an integer number, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}if (!Number.isInteger(jsonable)) {{
{II}return newDeserializationError<number>(
{III}`Expected an integer number, but got: ${{jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_float_from_jsonable() -> Stripped:
    """Generate the function to decode a ``float`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a number.
 *
 * @param jsonable - to be parsed
 * @returns parsed numeric value, or an error
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function numberFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<number, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<number>(
{III}"Expected a number, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "number") {{
{II}return newDeserializationError<number>(
{III}`Expected a number, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so a conformant parser
{I}// can never give us one. The caller can still hand us a JSON-able which has
{I}// been constructed programmatically, so we have to check here.
{I}if (!Number.isFinite(jsonable)) {{
{II}return newDeserializationError<number>(
{III}`Expected a finite number, but got: ${{jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<number, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_str_from_jsonable() -> Stripped:
    """Generate the function to decode a ``str`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a string.
 *
 * @param jsonable - to be parsed
 * @returns parsed string value, or an error
 */
function stringFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<string, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<string>(
{III}"Expected a string, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "string") {{
{II}return newDeserializationError<string>(
{III}`Expected a string, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<string, DeserializationError>(jsonable, null);
}}"""
    )


def _generate_bytes_from_jsonable() -> Stripped:
    """Generate the function to decode ``bytes`` from a JSON-able."""
    return Stripped(
        f"""\
/**
 * Parse `jsonable` as a byte array.
 *
 * @param jsonable - to be parsed
 * @returns parsed byte array, or an error
 */
function bytesFromJsonable(
{I}jsonable: JsonValue
): AasCommon.Either<Uint8Array, DeserializationError> {{
{I}if (jsonable === null) {{
{II}return newDeserializationError<Uint8Array>(
{III}"Expected a base64-encoded string, but got null"
{II});
{I}}}
{I}if (typeof jsonable !== "string") {{
{II}return newDeserializationError<Uint8Array>(
{III}`Expected a base64-encoded string, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}const either = AasCommon.base64Decode(jsonable);
{I}if (either.error !== null) {{
{II}return newDeserializationError<Uint8Array>(either.error);
{I}}}
{I}return new AasCommon.Either<Uint8Array, DeserializationError>(
{II}either.mustValue(), null
{I});
}}"""
    )


def _generate_enumeration_from_jsonable(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the deserialization method for an enumeration."""
    enum_name = typescript_naming.enum_name(identifier=enumeration.name)

    function_name = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_jsonable")
    )

    enum_from_str = typescript_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    return Stripped(
        f"""\
/**
 * Parse `jsonable` structure as a literal
 * of {{@link {typescript_common.TYPES_MODULE}!{enum_name}}}.
 *
 * @param jsonable - to be parsed
 * @returns parsed literal, or an error if `jsonable` invalid
 */
export function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<AasTypes.{enum_name}, DeserializationError> {{
{I}if (typeof jsonable !== "string") {{
{II}return newDeserializationError<AasTypes.{enum_name}>(
{III}`Expected a string, but got: ${{typeof jsonable}}`
{II});
{I}}}

{I}const literal = AasStringification.{enum_from_str}(jsonable);
{I}if (literal === null) {{
{II}return newDeserializationError<AasTypes.{enum_name}>(
{III}"Not a valid string representation of " +
{IIII}`a literal of {enum_name}: ${{jsonable}}`
{II});
{I}}}

{I}return new AasCommon.Either<
{II}AasTypes.{enum_name},
{II}DeserializationError
{I}>(literal, null);
}}"""
    )


def _parse_properties_function_name(cls: intermediate.ConcreteClass) -> Identifier:
    """Give out the name of the function parsing the properties of ``cls``."""
    return typescript_naming.function_name(
        Identifier(f"parse_properties_of_{cls.name}")
    )


def _generate_dispatch_case(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the ``switch`` case dispatching on the model type of ``cls``.

    The case calls the parser of the properties directly, so a dispatched instance
    is neither cast nor checked for its model type a second time, and no dispatching
    function can be re-entered.

    An implementation-specific class has no parser of its properties -- its whole
    function comes from a snippet -- so its own function is called instead. It takes
    a ``JsonValue``, of which a ``JsonObject`` is one.
    """
    model_type_literal = typescript_common.string_literal(
        naming.json_model_type(cls.name)
    )

    if cls.is_implementation_specific:
        callee = typescript_naming.function_name(
            Identifier(f"{cls.name}_from_jsonable")
        )
    else:
        callee = _parse_properties_function_name(cls)

    return Stripped(
        f"""\
case {model_type_literal}:
{I}return {callee}(jsonObject);"""
    )


def _generate_dispatch_on_model_type(
    type_name: Identifier,
    implementers: Sequence[intermediate.ConcreteClass],
) -> Stripped:
    """
    Generate the body which dispatches on the model type of the JSON object.

    The ``jsonObject`` is expected to be in scope. We branch with a ``switch``
    rather than with a map of the parsers, for the same reasons as in
    :py:func:`_generate_parse_properties_of_class`: a string ``switch`` compares
    interned strings, which is a comparison of pointers, and every case is a call
    site of its own and hence monomorphic, where a map has to call through a single
    site shared by every implementer. Measured on V8, the map does not pay off here
    either -- the ``switch`` takes about two thirds of its time even at
    38 implementers.
    """
    cases = [_generate_dispatch_case(implementer) for implementer in implementers]

    cases.append(
        Stripped(
            f"""\
default:
{I}return newDeserializationError<AasTypes.{type_name}>(
{II}`Unexpected model type for {type_name}: ${{modelType}}`
{I});"""
        )
    )

    cases_joined = "\n\n".join(cases)

    return Stripped(
        f"""\
const modelTypeOrError = extractModelType(jsonObject);
if (modelTypeOrError.error !== null) {{
{I}return new AasCommon.Either<
{II}AasTypes.{type_name},
{II}DeserializationError
{I}>(
{II}null,
{II}modelTypeOrError.error
{I});
}}

const modelType = modelTypeOrError.mustValue();

switch (modelType) {{
{I}{indent_but_first_line(cases_joined, I)}
}}"""
    )


def _generate_dispatch_from_jsonable(interface: intermediate.Interface) -> Stripped:
    """Generate the de-serialization dispatch for an abstract class."""
    function_name = typescript_naming.function_name(
        Identifier(f"{interface.name}_from_jsonable")
    )

    interface_name = typescript_naming.interface_name(interface.name)

    dispatch = _generate_dispatch_on_model_type(
        type_name=interface_name, implementers=interface.implementers
    )

    return Stripped(
        f"""\
/**
 * Parse `jsonable` as an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{interface_name}}}.
 *
 * @param jsonable - to be parsed
 * @returns parsed instance, or error if `jsonable` is invalid
 */
export function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<
{I}AasTypes.{interface_name},
{I}DeserializationError
> {{
{I}const objectError = checkIsJsonObject(jsonable);
{I}if (objectError !== null) {{
{II}return new AasCommon.Either<
{III}AasTypes.{interface_name},
{III}DeserializationError
{II}>(
{III}null,
{III}objectError
{II});
{I}}}
{I}const jsonObject = <JsonObject>jsonable;

{I}{indent_but_first_line(dispatch, I)}
}}"""
    )


def _generate_named_union_from_jsonable(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the de-serialization dispatch for the named union.

    We dispatch on ``modelType`` for every implementer which sets it, and
    fall back to testing which implementer's required properties are all
    present for the remaining implementers. This mirrors the per-implementer
    partitioning which we already verified in the intermediate
    representation, so every implementer is covered by exactly one of the
    two strategies.
    """
    function_name = typescript_naming.function_name(
        Identifier(f"{named_union.name}_from_jsonable")
    )

    union_name = typescript_naming.union_name(named_union.name)

    with_model_type = [
        implementer
        for implementer in named_union.implementers
        if implementer.serialization.with_model_type
    ]
    without_model_type = [
        implementer
        for implementer in named_union.implementers
        if not implementer.serialization.with_model_type
    ]

    blocks = [
        Stripped(
            f"""\
const objectError = checkIsJsonObject(jsonable);
if (objectError !== null) {{
{I}return new AasCommon.Either<
{II}AasTypes.{union_name},
{II}DeserializationError
{I}>(
{II}null,
{II}objectError
{I});
}}
const jsonObject = <JsonObject>jsonable;"""
        )
    ]  # type: List[Stripped]

    if len(with_model_type) > 0:
        # NOTE (mristin):
        # The model type is optional here, since the remaining implementers are
        # told apart structurally, so we test for its presence before reading it.
        dispatch = _generate_dispatch_on_model_type(
            type_name=union_name, implementers=with_model_type
        )

        blocks.append(
            Stripped(
                f"""\
if (jsonObject["modelType"] !== undefined) {{
{I}{indent_but_first_line(dispatch, I)}
}}"""
            )
        )
    else:
        # NOTE (mristin):
        # None of the implementers of this named union set ``modelType``, so
        # a ``modelType`` property on the wire can never be legitimate --
        # report it immediately instead of silently falling through to the
        # structural checks below.
        blocks.append(
            Stripped(
                f"""\
const modelType = jsonObject["modelType"];
if (modelType !== undefined) {{
{I}return newDeserializationError<AasTypes.{union_name}>(
{II}`Unexpected model type for {union_name}: ${{modelType}}`
{I});
}}"""
            )
        )

    for implementer in without_model_type:
        required_json_names = [
            implementer.properties_by_name[arg.name].json_name
            for arg in implementer.constructor.arguments
            if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
        ]
        assert len(required_json_names) > 0, (
            f"Expected the structurally-dispatched implementer "
            f"{implementer.name!r} of the named union {named_union.name!r} "
            f"to have at least one required property; this should have "
            f"already been verified in the intermediate representation."
        )

        # NOTE (mristin):
        # We call the parser of the properties directly. The implementer has no
        # model type -- that is why it is told apart structurally in the first
        # place -- so it has nothing left to dispatch on, and ``jsonObject`` has
        # already been cast.
        if implementer.is_implementation_specific:
            implementer_call = Stripped(
                f"""\
{typescript_naming.function_name(
    Identifier(f"{implementer.name}_from_jsonable")
)}(jsonObject)"""
            )
        else:
            implementer_call = Stripped(
                f"{_parse_properties_function_name(implementer)}(jsonObject)"
            )

        conditions = [
            f"jsonObject[{typescript_common.string_literal(json_name)}] "
            f"!== undefined"
            for json_name in required_json_names
        ]

        one_liner = f"if ({' && '.join(conditions)}) {{"
        if len(one_liner) <= 70:
            if_stmt = Stripped(one_liner)
        else:
            joined_conditions = "\n&& ".join(conditions)
            if_stmt = Stripped(
                f"""\
if (
{II}{indent_but_first_line(joined_conditions, II)}
) {{"""
            )

        blocks.append(
            Stripped(
                f"""\
{if_stmt}
{I}return {implementer_call};
}}"""
            )
        )

    blocks.append(
        Stripped(
            f"""\
return newDeserializationError<AasTypes.{union_name}>(
{I}"Could not determine the concrete type of {union_name} for the " +
{II}"given JSON object"
);"""
        )
    )

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
/**
 * Parse `jsonable` as an instance
 * of {{@link {typescript_common.TYPES_MODULE}!{union_name}}}.
 *
 * @param jsonable - to be parsed
 * @returns parsed instance, or error if `jsonable` is invalid
 */
function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<
{I}AasTypes.{union_name},
{I}DeserializationError
> {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


_PARSE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "booleanFromJsonable",
    intermediate.PrimitiveType.INT: "integerFromJsonable",
    intermediate.PrimitiveType.FLOAT: "numberFromJsonable",
    intermediate.PrimitiveType.STR: "stringFromJsonable",
    intermediate.PrimitiveType.BYTEARRAY: "bytesFromJsonable",
}
assert all(
    literal in _PARSE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _parse_function_for_atomic_value(
    type_annotation: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """Determine the parse function for deserializing an atomic non-optional value."""
    function_name: str

    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        function_name = _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[type_annotation.a_type]

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            function_name = typescript_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        elif isinstance(
            our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            if our_type.interface is not None:
                assert our_type.interface.name == our_type.name, (
                    "Assume that the interface name and the class name in "
                    "the intermediate representation are the same, so that the "
                    "``*_from_jsonable`` name makes sense in all cases"
                )

            function_name = typescript_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            function_name = _PARSE_FUNCTION_BY_PRIMITIVE_TYPE[our_type.constrainee]

        elif isinstance(our_type, intermediate.NamedUnion):
            function_name = typescript_naming.function_name(
                Identifier(f"{our_type.name}_from_jsonable")
            )

        else:
            assert_never(our_type)
    else:
        assert_never(type_annotation)

    return Stripped(function_name)


def _generate_parse_call_for_property(prop: intermediate.Property) -> Stripped:
    """
    Generate the call which de-serializes the value of ``prop``.

    Every de-serialization has one and the same shape, ``(jsonable: JsonValue) =>
    AasCommon.Either<T, DeserializationError>``, and ``jsonableValue`` already is
    the whole value of the property -- unlike in XML, a JSON value is not framed by
    anything -- so there is nothing to compose at the point of the call. A list and
    a tuple are the only two which take more than the value, and they take the
    parsers of their items as bare references, so no closure is allocated here
    either.

    We deliberately do not give a list a parser of its own named after its item
    type, as the C#, Java and Python generators do, and as the XML side has to.
    A ``supplementalSemanticIds`` would then read::

        parse_ListOf_Reference(jsonableValue)

    instead of::

        parseArray(jsonableValue, referenceFromJsonable)

    and the module would carry one such function per *distinct item type* --
    eighteen of them on the AAS meta-model, between them covering all of its
    124 list-typed properties. They are named by the moniker of the item type,
    exactly as on the XML side: ``parse_ListOf_Reference``,
    ``parse_ListOf_Extension``, ``parse_ListOf_ISubmodelElement``, and so on.
    Each one would be a copy of the loop of ``parseArray`` with ``parseItem``
    replaced by the parser of its item::

        function parse_ListOf_Reference(
          jsonable: JsonValue
        ): AasCommon.Either<Array<AasTypes.Reference>, DeserializationError> {
          // ... the very body of ``parseArray``, except that the item is parsed
          // by ``referenceFromJsonable`` instead of by ``parseItem``
        }

    That copy is the whole point of the exercise: it would monomorphise the call
    of the item parser, which is megamorphic in the shared ``parseArray`` -- one
    call site there serves every item type of the meta-model. A function which
    merely forwarded to ``parseArray`` would buy nothing, as V8 does not inline
    it.

    It is not worth it here. An item of a list in a meta-model is a whole class
    whose parsing dwarfs that one call: on the AAS meta-model the eighteen
    parsers measured within the noise of the de-serialization of an environment,
    for some 560 more lines of output.

    The arguments always go one per line. The consuming project runs Prettier over
    the generated code, which joins back whatever fits on one, so measuring the
    width here would only make the generator harder to read for no effect on
    the code which is finally compiled.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(
        type_anno,
        (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
    ):
        parse_function = _parse_function_for_atomic_value(type_anno)

        return Stripped(
            f"""\
{parse_function}(
{I}jsonableValue
)"""
        )

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            "We chose to implement only a very limited pattern matching; "
            "see intermediate._translate_._verify_only_simple_type_patterns"
        )

        parse_item_function = _parse_function_for_atomic_value(type_anno.items)

        return Stripped(
            f"""\
parseArray(
{I}jsonableValue,
{I}{parse_item_function}
)"""
        )

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_types = []  # type: List[Stripped]
        item_parse_functions = []  # type: List[str]
        for item_type_anno in type_anno.items:
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            item_types.append(
                typescript_common.generate_type(
                    item_type_anno, types_module=Identifier("AasTypes")
                )
            )
            item_parse_functions.append(
                _parse_function_for_atomic_value(item_type_anno)
            )

        item_types_joined = ", ".join(item_types)
        item_parse_functions_joined = ",\n".join(
            f"{I}{item_parse_function}" for item_parse_function in item_parse_functions
        )

        return Stripped(
            f"""\
parseTuple{len(type_anno.items)}<{item_types_joined}>(
{I}jsonableValue,
{item_parse_functions_joined}
)"""
        )

    assert_never(type_anno)


def _generate_parse_case(
    json_name: str, var_name: Identifier, call: Stripped
) -> Stripped:
    """
    Generate the ``switch`` case which de-serializes the property ``json_name``.

    Both halves of the result are taken unconditionally. On a failure the value is
    ``null``, and the property loop returns as soon as it sees the error, so what we
    assign to the variable is never read.
    """
    return Stripped(
        f"""\
case {typescript_common.string_literal(json_name)}: {{
{I}const parsed = {indent_but_first_line(call, I)};
{I}propertyError = parsed.error;
{I}{var_name} = parsed.value;
{I}break;
}}"""
    )


def _generate_parse_properties_of_class(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the function parsing the properties of a concrete class.

    The ``modelType``, if the class carries one, is expected to have been verified
    by the caller -- by a dispatcher, which matched it in order to arrive here at
    all, or by the public function of the class -- so it is only skipped here.

    The properties are de-serialized straight into the locals which the constructor
    is called with, since the loop is generated per class and a shared one could not
    write the locals of its caller.

    We branch with a ``switch`` rather than with a map of the parsers. A string
    ``switch`` is a chain of comparisons on V8 and hence linear in the number of
    the properties, where a map is not, but the comparisons are of interned strings
    and thus of pointers, and every case is a call site of its own and hence
    monomorphic, where a map has to call through a single site shared by every
    property. Measured on V8, the map does not pay off at any shape: the ``switch``
    takes a third of the time at six properties and about a half at twenty, and it
    stays ahead even when the input carries five times more unknown keys than
    known ones.
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
        "(mristin) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    cls_name = typescript_naming.class_name(cls.name)

    var_declarations = []  # type: List[Stripped]
    required_checks = []  # type: List[Stripped]
    parse_cases = []  # type: List[Stripped]

    var_name_by_property = {}  # type: Dict[Identifier, Identifier]

    for prop in cls.properties:
        var_name = typescript_naming.variable_name(Identifier(f"the_{prop.name}"))
        var_name_by_property[prop.name] = var_name

        var_type = typescript_common.generate_type(
            prop.type_annotation, types_module=Identifier("AasTypes")
        )

        # NOTE (mristin):
        # We make all the variables optional since the properties can come in any
        # order, so we can not tell a missing one from one which we have not read yet.
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            var_type = Stripped(f"{var_type} | null")

            message_literal = typescript_common.string_literal(
                f"The required property {prop.json_name!r} is missing"
            )
            required_checks.append(
                Stripped(
                    f"""\
if ({var_name} === null) {{
{I}return newDeserializationError<
{II}AasTypes.{cls_name}
{I}>(
{II}{message_literal}
{I});
}}"""
                )
            )

        var_declarations.append(Stripped(f"let {var_name}: {var_type} = null;"))

        parse_cases.append(
            _generate_parse_case(
                json_name=prop.json_name,
                var_name=var_name,
                call=_generate_parse_call_for_property(prop),
            )
        )

    if cls.serialization.with_model_type:
        model_type_literal = typescript_common.string_literal(
            naming.json_property(Identifier("model_type"))
        )

        parse_cases.append(
            Stripped(
                f"""\
case {model_type_literal}: {{
{I}// The model type has already been verified by the caller.
{I}break;
}}"""
            )
        )

    blocks = []  # type: List[Stripped]

    if len(parse_cases) > 0:
        blocks.append(Stripped("\n".join(var_declarations)))

        parse_cases.append(
            Stripped(
                f"""\
// NOTE (mristin):
// Since we conflate here a JavaScript object with a JSON object, we ignore
// properties which we do not know how to de-serialize and assume they are
// related to the *JavaScript* properties of the object or `Object` prototype.
default: {{
{I}continue;
}}"""
            )
        )

        parse_cases_joined = "\n\n".join(parse_cases)

        # NOTE (mristin):
        # The property name is marked on the error once, after the ``switch``, since
        # a case is matched exactly when ``key`` is its literal, so the two are one
        # and the same name.
        blocks.append(
            Stripped(
                f"""\
for (const key in jsonObject) {{
{I}const jsonableValue = jsonObject[key];

{I}let propertyError: DeserializationError | null = null;
{I}switch (key) {{
{II}{indent_but_first_line(parse_cases_joined, II)}
{I}}}

{I}if (propertyError !== null) {{
{II}propertyError.path.prepend(
{III}new PropertySegment(jsonObject, key)
{II});
{II}return new AasCommon.Either<
{III}AasTypes.{cls_name},
{III}DeserializationError
{II}>(
{III}null,
{III}propertyError
{II});
{I}}}
}}"""
            )
        )

    if len(required_checks) > 0:
        blocks.append(Stripped("\n\n".join(required_checks)))

    if len(cls.constructor.arguments) == 0:
        blocks.append(
            Stripped(
                f"""\
return new AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
>(
{I}new AasTypes.{cls_name}(),
{I}null
);"""
            )
        )
    else:
        init_writer = io.StringIO()
        init_writer.write(
            f"""\
return new AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
>(
{I}new AasTypes.{cls_name}(
"""
        )

        for i, arg in enumerate(cls.constructor.arguments):
            init_writer.write(f"{II}{var_name_by_property[arg.name]}")

            if i < len(cls.constructor.arguments) - 1:
                init_writer.write(",\n")
            else:
                init_writer.write("\n")

        init_writer.write(
            f"""\
{I}),
{I}null
);"""
        )

        blocks.append(Stripped(init_writer.getvalue()))

    function_name = _parse_properties_function_name(cls)

    description_blocks = [
        Stripped(
            f"""\
Parse the properties of an instance
of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}} from `jsonObject`."""
        )
    ]  # type: List[Stripped]

    if cls.serialization.with_model_type:
        description_blocks.append(
            Stripped(
                """\
The `modelType` is expected to have been already verified by the caller,
and is therefore skipped here."""
            )
        )

    description_blocks.append(
        Stripped(
            f"""\
@param jsonObject - JSON object to be parsed
@returns parsed instance of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}},
or an error if any"""
        )
    )

    description_comment = typescript_description.documentation_comment(
        Stripped("\n\n".join(description_blocks))
    )

    writer = io.StringIO()
    writer.write(
        f"""\
{description_comment}
function {function_name}(
{I}jsonObject: JsonObject
): AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
> {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


@require(lambda cls: len(cls.concrete_descendants) == 0)
def _generate_concrete_class_from_jsonable(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the public de-serialization function for a concrete class.

    A class with concrete descendants gets a dispatching function under this very
    name instead, see :py:func:`_generate_dispatch_from_jsonable`, so there is no
    dispatch left to perform here.
    """
    cls_name = typescript_naming.class_name(cls.name)

    function_name = typescript_naming.function_name(
        Identifier(f"{cls.name}_from_jsonable")
    )

    blocks = [
        Stripped(
            f"""\
const objectError = checkIsJsonObject(jsonable);
if (objectError !== null) {{
{I}return new AasCommon.Either<
{II}AasTypes.{cls_name},
{II}DeserializationError
{I}>(
{II}null,
{II}objectError
{I});
}}
const jsonObject = <JsonObject>jsonable;"""
        )
    ]  # type: List[Stripped]

    if cls.serialization.with_model_type:
        # NOTE (mristin):
        # The model type is verified in front of the property loop so that we fail
        # fast: a wrong one is reported without de-serializing any of the properties
        # first. We verify it even though a dispatcher may have read it already, as
        # a dispatch is not always necessary -- the caller may know the expected
        # runtime type -- while the model type can be invalid in the input all
        # the same.
        model_type = naming.json_model_type(cls.name)

        blocks.append(
            Stripped(
                f"""\
const modelTypeError = checkModelType(jsonObject, "{model_type}");
if (modelTypeError !== null) {{
{I}return new AasCommon.Either<
{II}AasTypes.{cls_name},
{II}DeserializationError
{I}>(
{II}null,
{II}modelTypeError
{I});
}}"""
            )
        )

    blocks.append(
        Stripped(f"return {_parse_properties_function_name(cls)}(jsonObject);")
    )

    description_comment = typescript_description.documentation_comment(
        Stripped(
            f"""\
Parse an instance of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}} from the JSON-able
structure `jsonable`.

@param jsonable - structure to be parsed
@returns parsed instance of {{@link {typescript_common.TYPES_MODULE}!{cls_name}}},
or an error if any"""
        )
    )

    writer = io.StringIO()
    writer.write(
        f"""\
{description_comment}
export function {function_name}(
{I}jsonable: JsonValue
): AasCommon.Either<
{I}AasTypes.{cls_name},
{I}DeserializationError
> {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


# endregion

# region Serialization


def _generate_transform_atomic_value(
    access_expression: str, type_anno: intermediate.AtomicTypeAnnotation
) -> Stripped:
    """
    Generate the snippet to transform the ``access_expression``.

    The ``access_expression`` should either be a name or a member access.
    """
    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive)
    ):
        a_type = intermediate.try_primitive_type(type_anno)
        assert a_type is not None

        if (
            a_type is intermediate.PrimitiveType.BOOL
            or a_type is intermediate.PrimitiveType.STR
        ):
            return Stripped(f"{access_expression}")

        elif a_type is intermediate.PrimitiveType.INT:
            return Stripped(f"integerToJsonable({access_expression})")

        elif a_type is intermediate.PrimitiveType.FLOAT:
            return Stripped(f"numberToJsonable({access_expression})")

        elif a_type is intermediate.PrimitiveType.BYTEARRAY:
            return Stripped(f"AasCommon.base64Encode({access_expression})")

        else:
            assert_never(a_type)

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            must_to_str_name = typescript_naming.function_name(
                Identifier(f"must_{type_anno.our_type.name}_to_string")
            )

            return Stripped(
                f"""\
AasStringification.{must_to_str_name}(
{I}{indent_but_first_line(access_expression, I)}
)"""
            )

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(
            type_anno.our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            return Stripped(f"this.transform({access_expression})")

        else:
            assert_never(type_anno.our_type)

    else:
        assert_never(type_anno.our_type)


def _generate_transform(
    cls: intermediate.ConcreteClass,
    ids_of_types_reaching_a_number: Set[intermediate.IdOfOurType],
) -> Stripped:
    """Generate the ``transformX`` method to serialize an instance into a JSON-able."""
    blocks = [Stripped("const jsonable: JsonObject = {};")]  # type: List[Stripped]

    for prop in cls.properties:
        key_literal = typescript_common.string_literal(prop.json_name)
        prop_name = typescript_naming.property_name(prop.name)

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        block: Stripped

        if isinstance(
            type_anno,
            (intermediate.PrimitiveTypeAnnotation, intermediate.OurTypeAnnotation),
        ):
            transformation_expression = _generate_transform_atomic_value(
                access_expression=Stripped(f"that.{prop_name}"), type_anno=type_anno
            )

            block = Stripped(
                f"""\
jsonable[{key_literal}] =
{I}{indent_but_first_line(transformation_expression, I)};"""
            )

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items,
                intermediate.AtomicTypeAnnotationAsTuple,
            ), (
                f"(mristin) We generate the JSON serialization code only for "
                f"the lists of atomic values at the moment, "
                f"but we got a list of type {type_anno}. "
                "Please contact the developers if you need this feature."
            )

            items_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if items_primitive_type in (
                intermediate.PrimitiveType.INT,
                intermediate.PrimitiveType.FLOAT,
            ):
                # NOTE (mristin):
                # A number has to be checked, so the items can not simply be
                # copied over. ``serializeArray`` records the index of the item
                # which is refused.
                item_serializer = (
                    "integerToJsonable"
                    if items_primitive_type is intermediate.PrimitiveType.INT
                    else "numberToJsonable"
                )

                block = Stripped(
                    f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}{item_serializer}
);"""
                )

            elif items_primitive_type is not None and (
                items_primitive_type != intermediate.PrimitiveType.BYTEARRAY
            ):
                # NOTE (mristin):
                # No transformation is needed for these primitive types, so we
                # do not even need ``serializeArray`` -- a defensive copy of
                # the items suffices.
                block = Stripped(
                    f"jsonable[{key_literal}] = Array.from(that.{prop_name});"
                )

            elif items_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                block = Stripped(
                    f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}AasCommon.base64Encode
);"""
                )

            elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                    must_to_str_name = typescript_naming.function_name(
                        Identifier(f"must_{type_anno.items.our_type.name}_to_string")
                    )

                    block = Stripped(
                        f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}AasStringification.{must_to_str_name}
);"""
                    )

                elif isinstance(
                    type_anno.items.our_type, intermediate.ConstrainedPrimitive
                ):
                    raise AssertionError("This case should have been handled before.")

                elif isinstance(
                    type_anno.items.our_type,
                    (
                        intermediate.AbstractClass,
                        intermediate.ConcreteClass,
                        intermediate.NamedUnion,
                    ),
                ):
                    # NOTE (mristin):
                    # ``this.transform`` needs a bound ``this``, so this is the
                    # one case where we can not pass a bare function reference.
                    block = Stripped(
                        f"""\
jsonable[{key_literal}] = serializeArray(
{I}that.{prop_name},
{I}(item) => this.transform(item)
);"""
                    )

                else:
                    assert_never(type_anno.items.our_type)

            else:
                raise NotImplementedError(
                    f"(mristin) We generate the JSON serialization code only for "
                    f"the lists of atomic values at the moment, "
                    f"but we got a list of type {type_anno}. "
                    "Please contact the developers if you need this feature."
                )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_expressions = []  # type: List[Stripped]
            for i, item_type_anno in enumerate(type_anno.items):
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    "Tuple items are restricted to atomic types (primitives, "
                    "constrained primitives, classes and enumerations) by "
                    "intermediate._translate._verify_only_simple_type_patterns, so no "
                    "nested optionals, lists or tuples are expected here."
                )

                item_expressions.append(
                    _generate_transform_atomic_value(
                        access_expression=Stripped(f"that.{prop_name}[{i}]"),
                        type_anno=item_type_anno,
                    )
                )

            item_is_fallible = [
                intermediate.reaches_a_number(
                    item_type_anno, ids_of_types_reaching_a_number
                )
                for item_type_anno in type_anno.items
            ]

            if not any(item_is_fallible):
                item_expressions_joined = ",\n".join(item_expressions)

                block = Stripped(
                    f"""\
jsonable[{key_literal}] = [
{I}{indent_but_first_line(item_expressions_joined, I)}
];"""
                )
            else:
                # NOTE (mristin):
                # An array literal can not record which item was refused, so
                # the items are pushed one by one, each under its own position.
                items_var = typescript_naming.variable_name(
                    Identifier(f"{prop.name}_items")
                )

                push_statements = []  # type: List[Stripped]

                for i, (item_expression, is_fallible) in enumerate(
                    zip(item_expressions, item_is_fallible)
                ):
                    push_statement = Stripped(
                        f"""\
{items_var}.push(
{I}{indent_but_first_line(item_expression, I)}
);"""
                    )

                    if is_fallible:
                        push_statement = Stripped(
                            f"""\
try {{
{I}{indent_but_first_line(push_statement, I)}
}} catch (error) {{
{I}if (error instanceof SerializationError) {{
{II}error.prependIndex({i});
{I}}}
{I}throw error;
}}"""
                        )

                    push_statements.append(push_statement)

                push_statements_joined = "\n".join(push_statements)

                block = Stripped(
                    f"""\
const {items_var} = new Array<JsonValue>();
{push_statements_joined}
jsonable[{key_literal}] = {items_var};"""
                )

        else:
            assert_never(type_anno)

        # NOTE (mristin):
        # Only a value which can be refused at all is worth guarding. The property
        # is recorded here, and nowhere below, as nothing below knows through which
        # property the value was reached.
        if intermediate.reaches_a_number(
            prop.type_annotation, ids_of_types_reaching_a_number
        ):
            prop_name_literal = typescript_common.string_literal(prop_name)

            block = Stripped(
                f"""\
try {{
{I}{indent_but_first_line(block, I)}
}} catch (error) {{
{I}if (error instanceof SerializationError) {{
{II}error.prependProperty({prop_name_literal});
{I}}}
{I}throw error;
}}"""
            )

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            block = Stripped(
                f"""\
if (that.{prop_name} !== null) {{
{I}{indent_but_first_line(block, I)}
}}"""
            )

        blocks.append(block)

    if cls.serialization.with_model_type:
        model_type_literal = typescript_common.string_literal(
            naming.json_model_type(cls.name)
        )
        blocks.append(Stripped(f"""jsonable["modelType"] = {model_type_literal};"""))

    blocks.append(Stripped("return jsonable;"))

    method_name = typescript_naming.method_name(Identifier(f"transform_{cls.name}"))

    cls_name = typescript_naming.class_name(cls.name)

    writer = io.StringIO()

    writer.write(
        f"""\
/**
 * Serialize `that` to a JSON-able representation.
 *
 * @param that - instance to be serialization
 * @returns JSON-able representation
 */
{method_name}(
{I}that: AasTypes.{cls_name}
): JsonObject {{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_serialize_array() -> Stripped:
    """Generate the generic helper to serialize an iterable into a JSON array."""
    return Stripped(
        f"""\
/**
 * Serialize every item of `items` with `serializeItem` into a JSON-able
 * array.
 *
 * @param items - to be serialized
 * @param serializeItem - to serialize a single item of `items`
 * @returns JSON-able array
 * @typeParam T - type of a single item to be serialized
 * @typeParam J - type of a single item once serialized
 */
/**
 * Serialize `items` one by one, recording the index of the one which is refused.
 */
function serializeArray<T, J extends JsonValue>(
{I}items: Iterable<T>,
{I}serializeItem: (item: T) => J
): Array<J> {{
{I}const result = new Array<J>();
{I}let i = 0;
{I}for (const item of items) {{
{II}try {{
{III}result.push(serializeItem(item));
{II}}} catch (error) {{
{III}if (error instanceof SerializationError) {{
{IIII}error.prependIndex(i);
{III}}}
{III}throw error;
{II}}}
{II}i++;
{I}}}
{I}return result;
}}"""
    )


def _generate_serialization_error() -> Stripped:
    """Generate the error signalling that a value could not be serialized."""
    return Stripped(
        f"""\
/**
 * Signal that the JSON serialization could not be performed.
 *
 * The {{@link SerializationError.path}} points into the instance which was to be
 * serialized, and *not* into a JSON document -- at the point of the failure,
 * there is no document yet. For example, `.submodels[0].value` tells you that
 * the serialization broke on `that.submodels[0].value`.
 *
 * Mind that this path is a plain string, unlike the structured
 * {{@link Path}} of the de-serialization. A segment of the latter carries
 * the JSON value it was read from, and while serializing there is no such
 * value to carry.
 */
export class SerializationError extends Error {{
{I}private readonly _segments = new Array<string>();

{I}/**
{I} * Render the path to the erroneous value as a TypeScript access expression.
{I} */
{I}get path(): string {{
{II}return this._segments.join("");
{I}}}

{I}/**
{I} * Insert the access to the property `name` before the {{@link path}}.
{I} */
{I}prependProperty(name: string): void {{
{II}this._segments.unshift(`.${{name}}`);
{I}}}

{I}/**
{I} * Insert the access to the item at `index` before the {{@link path}}.
{I} */
{I}prependIndex(index: number): void {{
{II}this._segments.unshift(`[${{index}}]`);
{I}}}
}}"""
    )


def _collect_number_types(
    symbol_table: intermediate.SymbolTable,
) -> Set[intermediate.PrimitiveType]:
    """Collect the number types which occur anywhere in the meta-model."""
    result = set()  # type: Set[intermediate.PrimitiveType]

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                a_type = intermediate.try_primitive_type(type_anno)
                if (
                    a_type is intermediate.PrimitiveType.INT
                    or a_type is intermediate.PrimitiveType.FLOAT
                ):
                    result.add(a_type)

    return result


def _generate_number_serializers(
    number_types: Set[intermediate.PrimitiveType],
) -> List[Stripped]:
    """
    Generate the serializers of the numbers which JSON can not represent.

    Only the serializers which are actually called are generated, as an unused
    one would trip the linter of the generated code.
    """
    blocks = [
        Stripped(
            f"""\
/**
 * Serialize `that` integer to a JSON-able value.
 *
 * Only the integers in the range [-2^53 + 1, 2^53 - 1] are serialized. Outside
 * of it, an integer can not be exactly represented as a 64-bit floating-point
 * number, which is what the JSON de-serializers of the other languages read
 * a number into.
 *
 * @param that - integer to be serialized
 * @returns `that`, unchanged
 * @throws {{@link SerializationError}} if outside the range
 */
function integerToJsonable(that: number): number {{
{I}if (!Number.isFinite(that) || that < -9007199254740991 || that > 9007199254740991) {{
{II}throw new SerializationError(
{III}`The integer can not be serialized to JSON as it is outside ` +
{IIII}`the range [-2^53 + 1, 2^53 - 1]: ${{that}}`
{II});
{I}}}
{I}return that;
}}"""
        ),
        Stripped(
            f"""\
/**
 * Serialize `that` number to a JSON-able value.
 *
 * JSON knows neither an infinity nor a not-a-number, so we refuse to serialize
 * them instead of leaving it to `JSON.stringify` to write them out as `null`.
 *
 * @param that - number to be serialized
 * @returns `that`, unchanged
 * @throws {{@link SerializationError}} if not finite
 */
function numberToJsonable(that: number): number {{
{I}if (!Number.isFinite(that)) {{
{II}throw new SerializationError(
{III}`JSON knows neither an infinity nor a not-a-number, so the value ` +
{IIII}`can not be serialized: ${{that}}`
{II});
{I}}}
{I}return that;
}}"""
        ),
    ]

    return [
        block
        for a_type, block in zip(
            (intermediate.PrimitiveType.INT, intermediate.PrimitiveType.FLOAT), blocks
        )
        if a_type in number_types
    ]


def _generate_transformer(
    symbol_table: intermediate.SymbolTable,
    ids_of_types_reaching_a_number: Set[intermediate.IdOfOurType],
) -> Stripped:
    methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        methods.append(_generate_transform(cls, ids_of_types_reaching_a_number))

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Transform the instance to its JSON-able representation.
 */
class Serializer extends AasTypes.AbstractTransformer<JsonObject> {
"""
    )

    for method in methods:
        writer.write("\n\n")
        writer.write(textwrap.indent(method, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


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
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for JSON de/serialization."""
    ids_of_types_reaching_a_number = (
        intermediate.collect_ids_of_types_reaching_a_number(symbol_table)
    )

    number_types = _collect_number_types(symbol_table)

    blocks = [
        typescript_description.documentation_comment(
            Stripped(
                """\
Provide de/serialization of AAS classes to/from JSON.

We can not use one-pass deserialization for JSON since the object
properties do not have fixed order, and hence we can not read
`modelType` property ahead of the remaining properties."""
            )
        ),
        typescript_common.WARNING,
        Stripped(
            """\
import * as AasCommon from "./common";
import * as AasTypes from "./types";
import * as AasStringification from "./stringification";"""
        ),
        Stripped(
            """\
export type JsonValue = string | number | boolean | JsonObject | JsonArray;

export type JsonArray = Iterable<JsonValue>;
export type JsonObject = { [prop: string]: JsonValue };"""
        ),
        Stripped(
            f"""\
/**
 * Represent a property on a path to the erroneous value.
 */
export class PropertySegment {{
{I}/**
{I} * Instance that contains the property
{I} */
{I}readonly instance: JsonObject;

{I}/**
{I} * Name of the property
{I} */
{I}readonly name: string;

{I}constructor(instance: JsonObject, name: string) {{
{II}this.instance = instance;
{II}this.name = name;
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Represent an index access on a path to the erroneous value.
 */
export class IndexSegment {{
{I}/**
{I} * Container that contains the item
{I} */
{I}readonly container: JsonArray;

{I}/**
{I} * Index of the item
{I} */
{I}readonly index: number;

{I}constructor(container: JsonArray, index: number) {{
{II}if (!Number.isInteger(index)) {{
{III}throw new Error(`Expected an integer for the index, but got: ${{index}}`);
{II}}}

{II}this.container = container;
{II}this.index = index;
{I}}}
}}"""
        ),
        Stripped(
            """\
export type Segment = PropertySegment | IndexSegment;"""
        ),
        Stripped(
            f"""\
/**
 * Represent the relative path to the erroneous value.
 */
export class Path {{
{I}private readonly _segments = new Array<Segment>();

{I}/**
{I} * Get the segments of the path.
{I} */
{I}segments(): Array<Segment> {{
{II}return this._segments;
{I}}}

{I}/**
{I} * Insert the `segment` in front of the {{@link segments}}.
{I} *
{I} * @param segment - segment to be prepended to {{@link segments}}
{I} */
{I}prepend(segment: Segment): void {{
{II}this._segments.unshift(segment);
{I}}}

{I}toString(): string {{
{II}if (this._segments.length === 0) {{
{III}return "";
{II}}}

{II}const parts = new Array<string>();

{II}let segment = this._segments[0];

{II}if (segment instanceof PropertySegment) {{
{III}parts.push(segment.name);
{II}}} else if (segment instanceof IndexSegment) {{
{III}parts.push(`[${{segment.index}}]`);
{II}}} else {{
{III}throw new Error(`Unexpected segment: ${{segment}}`);
{II}}}

{II}for (let i = 1; i < this._segments.length; i++) {{
{III}segment = this._segments[i];
{III}if (segment instanceof PropertySegment) {{
{IIII}parts.push(`.${{segment.name}}`);
{III}}} else if (segment instanceof IndexSegment) {{
{IIII}parts.push(`[${{segment.index}}]`);
{III}}} else {{
{IIII}throw new Error(`Unexpected segment: ${{segment}}`);
{III}}}
{II}}}

{II}return parts.join("");
{I}}}
}}"""
        ),
        Stripped("// region De-serialization"),
        Stripped(
            f"""\
/**
 * Signal that the JSON de-serialization could not be performed.
 */
export class DeserializationError {{
{I}/**
{I} * Human-readable explanation of the error
{I} */
{I}readonly message: string;

{I}/**
{I} * Relative path to the erroneous value
{I} */
{I}readonly path: Path;

{I}constructor(message: string, path: Path | null = null) {{
{II}this.message = message;
{II}this.path = path ?? new Path();
{I}}}
}}"""
        ),
        Stripped(
            f"""\
/**
 * Create an error as {{@link common.Either}}.
 *
 * @param message - human-readable explanation of the error
 * @returns An {{@link common.Either }} with the error set
 * @typeParam T - type of the value if there had been no error
 */
function newDeserializationError<T>(
{I}message: string
): AasCommon.Either<T, DeserializationError> {{
{I}return new AasCommon.Either<T, DeserializationError>(
{II}null,
{II}new DeserializationError(message)
{I});
}}"""
        ),
        _generate_check_is_json_object(),
        _generate_extract_model_type(),
        _generate_check_model_type(),
        _generate_check_is_iterable(),
        _generate_parse_array(),
        _generate_bool_from_jsonable(),
        _generate_int_from_jsonable(),
        _generate_float_from_jsonable(),
        _generate_str_from_jsonable(),
        _generate_bytes_from_jsonable(),
    ]  # type: List[Stripped]

    for arity in intermediate.tuple_arities(symbol_table=symbol_table):
        blocks.append(_generate_parse_tuple_helper(arity))

    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_enumeration_from_jsonable(enumeration=our_type))
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            pass
        elif isinstance(our_type, intermediate.AbstractClass):
            blocks.append(
                _generate_dispatch_from_jsonable(interface=our_type.interface)
            )
        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Jsonization/{our_type.name}_from_jsonable.ts"
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

                blocks.append(implementation)
            else:
                blocks.append(_generate_parse_properties_of_class(cls=our_type))

                if len(our_type.concrete_descendants) == 0:
                    blocks.append(_generate_concrete_class_from_jsonable(cls=our_type))

            if len(our_type.concrete_descendants) > 0:
                assert our_type.interface is not None
                blocks.append(
                    _generate_dispatch_from_jsonable(interface=our_type.interface)
                )

        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_named_union_from_jsonable(named_union=our_type))

        else:
            assert_never(our_type)

    blocks.append(Stripped("// endregion"))

    blocks.append(Stripped("// region Serialization"))

    blocks.append(_generate_serialization_error())

    blocks.extend(_generate_number_serializers(number_types))

    blocks.append(_generate_serialize_array())

    blocks.append(
        _generate_transformer(
            symbol_table=symbol_table,
            ids_of_types_reaching_a_number=ids_of_types_reaching_a_number,
        )
    )

    blocks.append(Stripped("const SERIALIZER = new Serializer();"))

    # pylint: disable=line-too-long
    blocks.append(
        Stripped(
            f"""\
/**
 * Convert `that` to a JSON-able structure.
 *
 * @param that - AAS data to be recursively converted to a JSON-able structure
 * @returns
 * JSON-able structure which can be further processed with, say,
 * {{@link https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/JSON/stringify|JSON.stringify}})
 */
export function toJsonable(that: AasTypes.Class): JsonObject {{
{I}return SERIALIZER.transform(that);
}}"""
        )
    )
    # pylint: enable=line-too-long

    blocks.append(Stripped("// endregion"))

    if len(errors) > 0:
        return None, errors

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
