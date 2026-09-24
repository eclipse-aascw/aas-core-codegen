"""Generate code for JSON de/serialization."""

import io
import itertools
from typing import List, Optional, Iterable, Final, Mapping, Set, Tuple

from icontract import ensure, require

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    Identifier,
    assert_never,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)


_MODEL_TYPE_LITERAL = "kModelType"


def _generate_deserialization_definitions(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the definitions of deserialization functions."""
    blocks = []  # type: List[Stripped]

    for cls in symbol_table.classes:
        interface_name = cpp_naming.interface_name(cls.name)
        deserialization_name = cpp_naming.function_name(Identifier(f"{cls.name}_from"))

        blocks.append(
            Stripped(
                f"""\
/**
 * \\brief Deserialize \\p json value to an instance
 * of types::{interface_name}.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return The deserialized instance, or a de-serialization error, if any.
 */
common::expected<
{I}std::shared_ptr<types::{interface_name}>,
{I}DeserializationError
> {deserialization_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties = false
);"""
            )
        )

    for named_union in symbol_table.named_unions:
        union_name = cpp_naming.union_name(named_union.name)
        deserialization_name = cpp_naming.function_name(
            Identifier(f"{named_union.name}_from")
        )

        blocks.append(
            Stripped(
                f"""\
/**
 * \\brief Deserialize \\p json value to an instance
 * of types::{union_name}.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return The deserialized instance, or a de-serialization error, if any.
 */
common::expected<
{I}types::{union_name},
{I}DeserializationError
> {deserialization_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties = false
);"""
            )
        )

    return blocks


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate header for JSON de/serialization."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.JSONIZATION_NAMESPACE}")

    include_guard_var = cpp_common.include_guard_var(namespace)

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/iteration.hpp"
#include "{include_prefix_path}/types.hpp"

#pragma warning(push, 0)
#include <nlohmann/json.hpp>

#include <memory>
#include <string>
#include <utility>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            f"""\
/**
 * \\defgroup jsonization De/serialize instances from and to JSON.
 * @{{
 */
namespace {cpp_common.JSONIZATION_NAMESPACE} {{"""
        ),
        Stripped(
            f"""\
/**
 * Represent a segment of a JSON path to some value.
 */
class ISegment {{
 public:
{I}/**
{I} * \\brief Convert the segment to a string in a JSON path.
{I} */
{I}virtual std::wstring ToWstring() const = 0;

{I}virtual std::unique_ptr<ISegment> Clone() const = 0;

{I}virtual ~ISegment() = default;
}};  // class ISegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent a property access on a JSON path.
 */
struct PropertySegment : public ISegment {{
{I}/**
{I} * Name of the property in a JSON object
{I} */
{I}std::wstring name;

{I}PropertySegment(
{II}std::wstring a_name
{I});

{I}std::wstring ToWstring() const override;

{I}std::unique_ptr<ISegment> Clone() const override;

{I}~PropertySegment() override = default;
}};  // struct PropertySegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent an index access on a JSON path.
 */
struct IndexSegment : public ISegment {{
{I}/**
{I} * Index of the value in an array.
{I} */
{I}size_t index;

{I}explicit IndexSegment(
{II}size_t an_index
{I});

{I}std::wstring ToWstring() const override;

{I}std::unique_ptr<ISegment> Clone() const override;

{I}~IndexSegment() override = default;
}};  // struct IndexSegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent a JSON path to some value.
 */
struct Path {{
{I}std::deque<std::unique_ptr<ISegment> > segments;

{I}Path();
{I}Path(const Path& other);
{I}Path(Path&& other);
{I}Path& operator=(const Path& other);
{I}Path& operator=(Path&& other);

{I}std::wstring ToWstring() const;
}};  // struct Path"""
        ),
        Stripped("// region De-serialization"),
        Stripped(
            f"""\
/**
 * Represent a de-serialization error.
 */
struct DeserializationError {{
{I}/**
{I} * Human-readable description of the error
{I} */
{I}std::wstring cause;

{I}/**
{I} * Path to the erroneous value
{I} */
{I}Path path;

{I}explicit DeserializationError(std::wstring a_cause);
{I}DeserializationError(std::wstring a_cause, Path a_path);
}};  // struct DeserializationError"""
        ),
        *_generate_deserialization_definitions(symbol_table=symbol_table),
        Stripped("// endregion Deserialization"),
        Stripped("// region Serialization"),
        Stripped(
            f"""\
/**
 * Represent an error in the serialization of an instance to JSON.
 */
class SerializationException : public std::exception {{
 public:
{I}SerializationException(
{II}std::wstring cause,
{II}iteration::Path path
{I});

{I}const char* what() const noexcept override;

{I}const std::wstring& cause() const noexcept;
{I}const iteration::Path& path() const noexcept;

{I}~SerializationException() noexcept override = default;

 private:
{I}const std::wstring cause_;
{I}const iteration::Path path_;
{I}const std::string msg_;
}};  // class SerializationException"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Serialize \\p that instance to a JSON value.
 *
 * \\param that instance to be serialized
 * \\return The corresponding JSON value
 * \\throw \\ref SerializationException if a value within \\p that instance
 * could not be serialized
 */
nlohmann::json Serialize(
{I}const types::IClass& that
);"""
        ),
        Stripped("// endregion Serialization"),
        Stripped(
            f"""\
}}  // namespace {cpp_common.JSONIZATION_NAMESPACE}
/**@}}*/"""
        ),
        cpp_common.generate_namespace_closing(library_namespace),
        cpp_common.WARNING,
        Stripped(f"#endif  // {include_guard_var}"),
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


def _generate_property_segment_implementation() -> List[Stripped]:
    """Generate the implementation of the struct ``PropertySegment``."""
    return [
        Stripped("// region PropertySegment"),
        Stripped(
            f"""\
PropertySegment::PropertySegment(
{I}std::wstring a_name
) :
{I}name(std::move(a_name)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
std::wstring PropertySegment::ToWstring() const {{
{I}return common::Concat(
{II}L".",
{II}name
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> PropertySegment::Clone() const {{
{I}return common::make_unique<PropertySegment>(*this);
}}"""
        ),
        Stripped("// endregion PropertySegment"),
    ]


def _generate_index_segment_implementation() -> List[Stripped]:
    """Generate the implementation of the struct ``IndexSegment``."""
    return [
        Stripped("// region IndexSegment"),
        Stripped(
            f"""\
IndexSegment::IndexSegment(
{I}size_t an_index
) :
{I}index(an_index) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
std::wstring IndexSegment::ToWstring() const {{
{I}return common::Concat(
{II}L"[",
{II}std::to_wstring(index),
{II}L"]"
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> IndexSegment::Clone() const {{
{I}return common::make_unique<IndexSegment>(*this);
}}"""
        ),
        Stripped("// endregion IndexSegment"),
    ]


def _generate_path_implementation() -> List[Stripped]:
    """Generate the implementation of the struct ``Path``."""
    return [
        Stripped("// region struct Path"),
        Stripped(
            f"""\
Path::Path() {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Path::Path(const Path& other) {{
{I}for (const std::unique_ptr<ISegment>& segment : other.segments) {{
{II}segments.emplace_back(segment->Clone());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
Path::Path(Path&& other) {{
{I}segments = std::move(other.segments);
}}"""
        ),
        Stripped(
            f"""\
Path& Path::operator=(const Path& other) {{
{I}segments.clear();
{I}for (const std::unique_ptr<ISegment>& segment : other.segments) {{
{II}segments.emplace_back(segment->Clone());
{I}}}
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
Path& Path::operator=(Path&& other) {{
{I}if (this != &other) {{
{II}segments = std::move(other.segments);
{I}}}
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
std::wstring Path::ToWstring() const {{
{I}if (segments.empty()) {{
{II}return L"";
{I}}}

{I}std::deque<std::wstring> parts;
{I}for (const std::unique_ptr<ISegment>& segment : segments ) {{
{II}parts.emplace_back(segment->ToWstring());
{I}}}

{I}size_t out_len = 0;
{I}for (const std::wstring& part : parts) {{
{II}out_len += part.size();
{I}}}

{I}std::wstring out;
{I}out.reserve(out_len);
{I}for (const std::wstring& part : parts) {{
{II}out.append(part);
{I}}}

{I}return out;
}}"""
        ),
        Stripped("// endregion struct Path"),
    ]


def _generate_deserialization_error_implementation() -> List[Stripped]:
    """Generate the impl. of the deserialization error class."""
    return [
        Stripped("// region class DeserializationError"),
        Stripped(
            f"""\
DeserializationError::DeserializationError(
{I}std::wstring a_cause
) :
{I}cause(a_cause) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
DeserializationError::DeserializationError(
{I}std::wstring a_cause,
{I}Path a_path
) :
{I}cause(a_cause),
{I}path(a_path) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped("// endregion class DeserializationError"),
    ]


def _generate_deserialize_bool() -> Stripped:
    """Generate the function to de-serialize a boolean from a JSON value."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<bool>,
{I}common::optional<DeserializationError>
> DeserializeBool(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_boolean()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a boolean, but got a value of type: ",
{III}common::Utf8ToWstring(json.type_name())
{II});

{II}return std::make_pair<
{III}common::optional<bool>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<bool>,
{II}common::optional<DeserializationError>
{I}>(
{II}json.get<bool>(),
{II}common::nullopt
{I});
}}"""
    )


def _generate_deserialize_int() -> Stripped:
    """Generate the function to de-serialize an int from a JSON value."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<int64_t>,
{I}common::optional<DeserializationError>
> DeserializeInt64(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_number()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected an integer number, but got a value of type: ",
{III}common::Utf8ToWstring(json.type_name())
{II});

{II}return std::make_pair<
{III}common::optional<int64_t>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}static_assert(
{II}std::is_same<nlohmann::json::number_integer_t, int64_t>::value,
{II}"Expected nlohmann::json::number_integer_t to equal int64_t, "
{II}"but it does not."
{I});

{I}if (json.is_number_integer()) {{
{II}return std::make_pair<
{III}common::optional<int64_t>,
{III}common::optional<DeserializationError>
{II}>(
{III}json.get<int64_t>(),
{III}common::nullopt
{II});
{I}}}

{I}if (json.is_number_unsigned()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a 64-bit integer number, "
{III}L"but got an unsigned integer number which does not fit in that range: ",
{III}std::to_wstring(json.get<nlohmann::json::number_unsigned_t>())
{II});

{II}return std::make_pair<
{III}common::optional<int64_t>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// We have to check that the number is an integer even though it can
{I}// not be stored in int64_t in order to give an informative message.

{I}const nlohmann::json::number_float_t number(
{II}json.get<nlohmann::json::number_float_t>()
{I});

{I}nlohmann::json::number_float_t integer_part;
{I}const bool is_integer(
{II}std::modf(number, &integer_part) == 0
{I});
{I}if (is_integer) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a 64-bit integer number, "
{III}L"but got an integer number which does not fit in that range: ",
{III}std::to_wstring(number)
{II});

{II}return std::make_pair<
{III}common::optional<int64_t>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}} else {{
{II}std::wstring message = common::Concat(
{III}L"Expected a 64-bit integer number, "
{III}L"but got a non-integer number: ",
{III}std::to_wstring(number)
{II});

{II}return std::make_pair<
{III}common::optional<int64_t>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}
}}"""
    )


def _generate_deserialize_float() -> Stripped:
    """Generate the function to de-serialize a float from a JSON value."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<double>,
{I}common::optional<DeserializationError>
> DeserializeDouble(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_number()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a number, but got a value of type: ",
{III}common::Utf8ToWstring(json.type_name())
{II});

{II}return std::make_pair<
{III}common::optional<double>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}static_assert(
{II}std::is_same<nlohmann::json::number_float_t, double>::value,
{II}"Expected nlohmann::json::number_float_t to equal double, "
{II}"but it does not."
{I});

{I}const double value(json.get<double>());

{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so a conformant parser
{I}// can never give us one. The caller can still hand us a JSON value which
{I}// has been constructed programmatically, so we have to check here.

{I}if (!std::isfinite(value)) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a finite number, but got: ",
{III}std::to_wstring(value)
{II});

{II}return std::make_pair<
{III}common::optional<double>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<double>,
{II}common::optional<DeserializationError>
{I}>(
{II}value,
{II}common::nullopt
{I});
}}"""
    )


def _generate_deserialize_str() -> Stripped:
    """Generate the function to de-serialize a string from a JSON value."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<std::wstring>,
{I}common::optional<DeserializationError>
> DeserializeWstring(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_string()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a string, but got a value of type: ",
{III}common::Utf8ToWstring(json.type_name())
{II});

{II}return std::make_pair<
{III}common::optional<std::wstring>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<std::wstring>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::Utf8ToWstring(*(json.get_ptr<const std::string*>())),
{II}common::nullopt
{I});
}}"""
    )


def _generate_deserialize_bytearray() -> Stripped:
    """Generate the function to de-serialize a bytearray from a JSON value."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<std::vector<std::uint8_t> >,
{I}common::optional<DeserializationError>
> DeserializeByteArray(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_string()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected a base64-encoded byte array as a string, "
{III}L"but got a value of type: ",
{III}common::Utf8ToWstring(json.type_name())
{II});;

{II}return std::make_pair<
{III}common::optional<std::vector<std::uint8_t> >,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}common::expected<
{II}std::vector<std::uint8_t>,
{II}std::string
{I}> bytes = stringification::Base64Decode(
{II}*(json.get_ptr<const std::string*>())
{I});

{I}if (!bytes.has_value()) {{
{II}std::wstring message = common::Concat(
{III}L"Failed to base64-decode the bytes from a string: ",
{III}common::Utf8ToWstring(bytes.error())
{II});

{II}return std::make_pair<
{III}common::optional<std::vector<std::uint8_t> >,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<std::vector<std::uint8_t> >,
{II}common::optional<DeserializationError>
{I}>(
{II}std::move(*bytes),
{II}common::nullopt
{I});
}}"""
    )


_PRIMITIVE_TYPE_TO_DESERIALIZE: Final[Mapping[intermediate.PrimitiveType, Stripped]] = {
    intermediate.PrimitiveType.BOOL: Stripped("DeserializeBool"),
    intermediate.PrimitiveType.INT: Stripped("DeserializeInt64"),
    intermediate.PrimitiveType.FLOAT: Stripped("DeserializeDouble"),
    intermediate.PrimitiveType.STR: Stripped("DeserializeWstring"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("DeserializeByteArray"),
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_TO_DESERIALIZE
    for primitive_type in intermediate.PrimitiveType
)


def _json_deserialize_function_for(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Determine the function to de-serialize the given JSON-able ``type_anno``."""
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Stripped("DeserializeJsonValue")
    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return Stripped("DeserializeJsonArray")
    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return Stripped("DeserializeJsonObject")
    else:
        raise AssertionError(
            f"Expected a JSON-able type annotation, but got: {type_anno}"
        )


def _json_serialize_function_for(
    type_anno: intermediate.TypeAnnotationUnion,
) -> Stripped:
    """Determine the function to serialize the given JSON-able ``type_anno``."""
    if isinstance(type_anno, intermediate.JsonValueTypeAnnotation):
        return Stripped("SerializeJsonValue")
    elif isinstance(type_anno, intermediate.JsonArrayTypeAnnotation):
        return Stripped("SerializeJsonArray")
    elif isinstance(type_anno, intermediate.JsonObjectTypeAnnotation):
        return Stripped("SerializeJsonObject")
    else:
        raise AssertionError(
            f"Expected a JSON-able type annotation, but got: {type_anno}"
        )


def _generate_deserialize_json_value() -> Stripped:
    """
    Generate the function to recursively de-serialize a JSON-able value.

    This rejects ``null``, a binary value and a discarded value -- none of
    which are representable as a ``JSONValue`` -- at any depth, but does not
    otherwise restrict the top-level shape (unlike
    :py:func:`_generate_deserialize_json_array`/
    :py:func:`_generate_deserialize_json_object`).
    """
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeJsonValue(
{I}const nlohmann::json& json
) {{
{I}if (json.is_null() || json.is_binary() || json.is_discarded()) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIIII}L"an array or an object), but got a value of type: ",
{IIIII}common::Utf8ToWstring(json.type_name())
{IIII})
{III})
{II});
{I}}}

{I}if (json.is_array()) {{
{II}nlohmann::json result(nlohmann::json::array());
{II}result.get_ref<nlohmann::json::array_t&>().reserve(json.size());

{II}size_t index = 0;
{II}for (const nlohmann::json& item : json) {{
{III}common::optional<nlohmann::json> deserialized_item;
{III}common::optional<DeserializationError> error;
{III}std::tie(deserialized_item, error) = DeserializeJsonValue(item);

{III}if (error.has_value()) {{
{IIII}error->path.segments.emplace_front(
{IIIII}common::make_unique<IndexSegment>(index)
{IIII});

{IIII}return std::make_pair(common::nullopt, std::move(error));
{III}}}

{III}result.push_back(std::move(*deserialized_item));
{III}++index;
{II}}}

{II}return std::make_pair(std::move(result), common::nullopt);
{I}}}

{I}if (json.is_object()) {{
{II}nlohmann::json result(nlohmann::json::object());

{II}for (const auto& item : json.items()) {{
{III}common::optional<nlohmann::json> deserialized_value;
{III}common::optional<DeserializationError> error;
{III}std::tie(deserialized_value, error) = DeserializeJsonValue(item.value());

{III}if (error.has_value()) {{
{IIII}error->path.segments.emplace_front(
{IIIII}common::make_unique<PropertySegment>(
{IIIIII}common::Utf8ToWstring(item.key())
{IIIII})
{IIII});

{IIII}return std::make_pair(common::nullopt, std::move(error));
{III}}}

{III}result[item.key()] = std::move(*deserialized_value);
{II}}}

{II}return std::make_pair(std::move(result), common::nullopt);
{I}}}

{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so we refuse both
{I}// instead of silently writing them out as ``null``, mirroring
{I}// ``DeserializeDouble`` for the floating-point properties of the model.
{I}// The caller gives us an ``nlohmann::json`` which may well have been
{I}// constructed programmatically, so a non-finite number can reach us
{I}// even though no conformant parser would ever produce one.
{I}if (json.is_number_float() && !std::isfinite(json.get<double>())) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON-able value, but got the number ",
{IIIII}std::to_wstring(json.get<double>()),
{IIIII}L", which is neither finite nor representable in JSON"
{IIII})
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// The value is a boolean, a number or a string, all of which are already
{I}// JSON-able as-is.
{I}return std::make_pair(json, common::nullopt);
}}"""
    )


def _generate_deserialize_json_array() -> Stripped:
    """Generate the function to de-serialize a JSON array of JSON-able values."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeJsonArray(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_array()) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON array, but got a value of type: ",
{IIIII}common::Utf8ToWstring(json.type_name())
{IIII})
{III})
{II});
{I}}}

{I}return DeserializeJsonValue(json);
}}"""
    )


def _generate_deserialize_json_object() -> Stripped:
    """Generate the function to de-serialize a JSON object of JSON-able values."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<DeserializationError>
> DeserializeJsonObject(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_object()) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON object, but got a value of type: ",
{IIIII}common::Utf8ToWstring(json.type_name())
{IIII})
{III})
{II});
{I}}}

{I}return DeserializeJsonValue(json);
}}"""
    )


def _generate_serialize_json_value() -> Stripped:
    """
    Generate the function to recursively serialize a JSON-able value.

    This re-validates the value even though it is already a
    ``nlohmann::json`` in memory, since ``nlohmann::json`` can represent
    shapes (``null``, a binary value, a discarded value) which are not
    representable as a ``JSONValue`` -- the constructor of a class instance
    does not, by itself, guard against these.
    """
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeJsonValue(
{I}const nlohmann::json& value
) {{
{I}if (value.is_null() || value.is_binary() || value.is_discarded()) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<SerializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIIII}L"an array or an object), but got a value of type: ",
{IIIII}common::Utf8ToWstring(value.type_name())
{IIII})
{III})
{II});
{I}}}

{I}if (value.is_array()) {{
{II}nlohmann::json result(nlohmann::json::array());
{II}result.get_ref<nlohmann::json::array_t&>().reserve(value.size());

{II}size_t index = 0;
{II}for (const nlohmann::json& item : value) {{
{III}common::optional<nlohmann::json> serialized_item;
{III}common::optional<SerializationError> error;
{III}std::tie(serialized_item, error) = SerializeJsonValue(item);

{III}if (error.has_value()) {{
{IIII}error->path.segments.emplace_front(
{IIIII}common::make_unique<iteration::IndexSegment>(index)
{IIII});

{IIII}return std::make_pair(common::nullopt, std::move(error));
{III}}}

{III}result.push_back(std::move(*serialized_item));
{III}++index;
{II}}}

{II}return std::make_pair(std::move(result), common::nullopt);
{I}}}

{I}if (value.is_object()) {{
{II}nlohmann::json result(nlohmann::json::object());

{II}for (const auto& item : value.items()) {{
{III}common::optional<nlohmann::json> serialized_value;
{III}common::optional<SerializationError> error;
{III}std::tie(serialized_value, error) = SerializeJsonValue(item.value());

{III}if (error.has_value()) {{
{IIII}error->path.segments.emplace_front(
{IIIII}common::make_unique<iteration::KeySegment>(
{IIIIII}common::Utf8ToWstring(item.key())
{IIIII})
{IIII});

{IIII}return std::make_pair(common::nullopt, std::move(error));
{III}}}

{III}result[item.key()] = std::move(*serialized_value);
{II}}}

{II}return std::make_pair(std::move(result), common::nullopt);
{I}}}

{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so we refuse both
{I}// instead of silently writing them out as ``null``, mirroring
{I}// ``SerializeDouble`` for the floating-point properties of the model.
{I}// The caller gives us an ``nlohmann::json`` which may well have been
{I}// constructed programmatically, so a non-finite number can reach us
{I}// even though no conformant parser would ever produce one.
{I}if (value.is_number_float() && !std::isfinite(value.get<double>())) {{
{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<SerializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<SerializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON-able value, but got the number ",
{IIIII}std::to_wstring(value.get<double>()),
{IIIII}L", which is neither finite nor representable in JSON"
{IIII})
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// The value is a boolean, a number or a string, all of which are already
{I}// JSON-able as-is.
{I}return std::make_pair(value, common::nullopt);
}}"""
    )


def _generate_serialize_json_array() -> Stripped:
    """Generate the function to serialize a JSON array of JSON-able values."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeJsonArray(
{I}const nlohmann::json& value
) {{
{I}if (!value.is_array()) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<SerializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON array, but got a value of type: ",
{IIIII}common::Utf8ToWstring(value.type_name())
{IIII})
{III})
{II});
{I}}}

{I}return SerializeJsonValue(value);
}}"""
    )


def _generate_serialize_json_object() -> Stripped:
    """Generate the function to serialize a JSON object of JSON-able values."""
    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeJsonObject(
{I}const nlohmann::json& value
) {{
{I}if (!value.is_object()) {{
{II}return std::make_pair(
{III}common::nullopt,
{III}common::make_optional<SerializationError>(
{IIII}common::Concat(
{IIIII}L"Expected a JSON object, but got a value of type: ",
{IIIII}common::Utf8ToWstring(value.type_name())
{IIII})
{III})
{II});
{I}}}

{I}return SerializeJsonValue(value);
}}"""
    )


def _generate_deserialize_list() -> Stripped:
    """Generate a generic list deserialization function."""
    return Stripped(
        f"""\
/**
 * \\brief De-serialize a list of items from \\p json.
 *
 * \\param json value expected to be an array
 * \\param deserialize_item de-serializes an item
 * \\return the list, or an error, if any
 */
template <typename T, typename DeserializeItemT>
std::pair<
{I}common::optional<std::vector<T> >,
{I}common::optional<DeserializationError>
> DeserializeList(
{I}const nlohmann::json& json,
{I}DeserializeItemT&& deserialize_item
) {{
{I}if (!json.is_array()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected an array, but got: ",
{III}common::Utf8ToWstring(
{IIII}json.type_name()
{III})
{II});

{II}return std::make_pair<
{III}common::optional<std::vector<T> >,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}common::optional<std::vector<T> > list(
{II}common::make_optional<std::vector<T> >()
{I});

{I}list->reserve(json.size());

{I}size_t index = 0;

{I}for(const nlohmann::json& item : json) {{
{II}common::optional<T> deserialized;
{II}common::optional<DeserializationError> error;

{II}std::tie(deserialized, error) = deserialize_item(item);

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<IndexSegment>(
{IIIII}index
{IIII})
{III});

{III}return std::make_pair<
{IIII}common::optional<std::vector<T> >,
{IIII}common::optional<DeserializationError>
{III}>(
{IIII}common::nullopt,
{IIII}std::move(error)
{III});
{II}}}

{II}list->emplace_back(std::move(*deserialized));

{II}++index;
{I}}}

{I}return std::make_pair(
{II}list,
{II}common::nullopt
{I});
}}"""
    )


def _generate_deserialize_list_of_instances() -> Stripped:
    """
    Generate the list de-serialization whose items are given the options.

    An instance and a named union are de-serialized with
    ``additional_properties`` handed down to them, everything else without, so
    the two differ in the arity of the item parser and not in anything else.
    """
    return Stripped(
        f"""\
/**
 * \\brief De-serialize a list of instances from \\p json.
 *
 * \\param json value expected to be an array
 * \\param additional_properties handed over to \\p deserialize_item
 * \\param deserialize_item de-serializes an item
 * \\return the list, or an error, if any
 */
template <typename T, typename DeserializeItemT>
std::pair<
{I}common::optional<std::vector<T> >,
{I}common::optional<DeserializationError>
> DeserializeList(
{I}const nlohmann::json& json,
{I}bool additional_properties,
{I}DeserializeItemT&& deserialize_item
) {{
{I}return DeserializeList<T>(
{II}json,
{II}[&additional_properties, &deserialize_item](
{III}const nlohmann::json& item
{II}) {{
{III}return deserialize_item(item, additional_properties);
{II}}}
{I});
}}"""
    )


def _generate_deserialize_tuple_function(arity: int) -> Stripped:
    """
    Generate a generic function to de-serialize a tuple of the given ``arity``.

    Each positional item is de-serialized by its own ``deserialize_item{i}``
    callable from the corresponding array item. The array-ness and length of
    ``json`` are checked once, up-front, mirroring how
    :py:func:`_generate_deserialize_list` checks that ``json`` is an array
    before looping over its items.
    """
    assert arity > 0

    # NOTE (mristin):
    # ``T{i}`` only appears in the return type (a non-deduced context), so it
    # must always be given explicitly at the call site, while
    # ``DeserializeItemT{i}`` is deduced from the corresponding callable
    # argument. Explicit template arguments bind positionally to the *first*
    # declared template parameters, so all the ``T{i}`` must precede all the
    # ``DeserializeItemT{i}`` for a call site that only specifies
    # ``T0, ..., T{arity-1}`` to work.
    template_params_joined = ",\n".join(
        [f"typename T{i}" for i in range(arity)]
        + [f"typename DeserializeItemT{i}" for i in range(arity)]
    )

    item_types_joined = ",\n".join(f"T{i}" for i in range(arity))

    parameters = ",\n".join(
        f"DeserializeItemT{i}&& deserialize_item{i}" for i in range(arity)
    )

    item_declarations = "\n".join(
        f"common::optional<T{i}> item{i};" for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
std::tie(
{I}item{i},
{I}error
) = deserialize_item{i}(
{I}json[{i}]
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<IndexSegment>(
{III}{i}
{II})
{I});
{I}return std::make_pair<
{II}common::optional<std::tuple<
{III}{indent_but_first_line(item_types_joined, III)}
{II}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    tuple_items_joined = ",\n".join(f"std::move(*item{i})" for i in range(arity))

    function_name = f"DeserializeTuple{arity}"

    return Stripped(
        f"""\
template <
{I}{indent_but_first_line(template_params_joined, I)}
>
std::pair<
{I}common::optional<std::tuple<
{II}{indent_but_first_line(item_types_joined, II)}
{I}> >,
{I}common::optional<DeserializationError>
> {function_name}(
{I}const nlohmann::json& json,
{I}{indent_but_first_line(parameters, I)}
) {{
{I}if (!json.is_array()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected an array, but got: ",
{III}common::Utf8ToWstring(
{IIII}json.type_name()
{III})
{II});

{II}return std::make_pair<
{III}common::optional<std::tuple<
{IIII}{indent_but_first_line(item_types_joined, IIII)}
{III}> >,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}if (json.size() != {arity}) {{
{II}std::wstring message = common::Concat(
{III}L"Expected exactly {arity} item(s) in the array, "
{III}L"but got: ",
{III}std::to_wstring(json.size())
{II});

{II}return std::make_pair<
{III}common::optional<std::tuple<
{IIII}{indent_but_first_line(item_types_joined, IIII)}
{III}> >,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}common::optional<DeserializationError> error;

{I}{indent_but_first_line(item_declarations, I)}

{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return std::make_pair(
{II}common::make_optional<std::tuple<
{III}{indent_but_first_line(item_types_joined, III)}
{II}> >(
{III}std::make_tuple(
{IIII}{indent_but_first_line(tuple_items_joined, IIII)}
{III})
{II}),
{II}common::nullopt
{I});
}}"""
    )


def _generate_get_model_type() -> Stripped:
    """Generate the getter of the model type from JSON object for dispatches."""
    return Stripped(
        f"""\
/**
 * Get the property `modelType` from the JSON value expected as a JSON object.
 */
std::pair<
{I}const std::string*,
{I}common::optional<DeserializationError>
> GetModelTypeFrom(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_object()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected an object, but got: ",
{III}common::Utf8ToWstring(json.type_name())
{II});

{II}return std::make_pair<
{III}const std::string*,
{III}common::optional<DeserializationError>
{II}>(
{III}nullptr,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}if (!json.contains("modelType")) {{
{II}return std::make_pair<
{III}const std::string*,
{III}common::optional<DeserializationError>
{II}>(
{III}nullptr,
{III}common::make_optional<DeserializationError>(
{IIII}L"The required property modelType is missing"
{III})
{II});
{I}}}

{I}const nlohmann::json& model_type_prop = json["modelType"];
{I}if (!model_type_prop.is_string()) {{
{II}std::wstring message = common::Concat(
{III}L"Expected modelType to be a string, but got: ",
{III}common::Utf8ToWstring(model_type_prop.type_name())
{II});

{II}common::optional<DeserializationError> error(
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{II}error->path.segments.emplace_front(
{III}common::make_unique<PropertySegment>(
{IIII}L"modelType"
{III})
{II});

{II}// NOTE (mristin):
{II}// We have to explicitly use the constructor instead of std::make_pair
{II}// as `const std::string*` can not be automatically converted to a rvalue.
{II}return std::pair<
{III}const std::string*,
{III}common::optional<DeserializationError>
{II}>(
{III}nullptr,
{III}error
{II});
{I}}}

{I}static_assert(
{II}std::is_same<nlohmann::json::string_t, std::string>::value,
{II}"Expected nlohmann::json::string_t to equal std::string, but it does not."
{I});

{I}const std::string* model_type(
{II}model_type_prop.get_ptr<const std::string*>()
{I});

{I}// NOTE (mristin):
{I}// We have to explicitly use the constructor instead of std::make_pair
{I}// as `const std::string*` can not be automatically converted to a rvalue.
{I}return std::pair<
{II}const std::string*,
{II}common::optional<DeserializationError>
{I}>(
{II}model_type,
{II}common::nullopt
{I});
}}"""
    )


def _generate_model_type_string_to_model_type(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate the mapping of the JSON ``modelType`` string to the model type.

    This mirrors ``model_type_from_element_name`` on the XML side: a single
    lookup covering *every* concrete class in the meta-model, generated once,
    so that dispatch functions can convert the ``modelType`` string to a
    ``types::ModelType`` and then ``switch`` on it (instead of routing through
    a ``std::map<std::string, std::function<...>>`` keyed by string per
    abstract class).
    """
    items = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        literal_name = cpp_naming.enum_literal_name(cls.name)

        model_type = naming.json_model_type(cls.name)

        items.append(
            Stripped(
                f"""\
{{
{I}{cpp_common.string_literal(model_type)},
{I}types::ModelType::{literal_name}
}}"""
            )
        )

    map_name = cpp_naming.constant_name(Identifier("model_type_string_to_model_type"))

    items_joined = ",\n".join(items)

    function_name = cpp_naming.function_name(
        Identifier("model_type_from_model_type_string")
    )

    return [
        Stripped(
            f"""\
/**
 * Map JSON \\c modelType strings to model types.
 */
const std::unordered_map<
{I}std::string,
{I}types::ModelType
> {map_name} = {{
{I}{indent_but_first_line(items_joined, I)}
}};"""
        ),
        Stripped(
            f"""\
common::optional<types::ModelType> {function_name}(
{I}const std::string& model_type_str
) {{
{I}auto it = {map_name}.find(model_type_str);
{I}if (it == {map_name}.end()) {{
{II}return common::nullopt;
{I}}}

{I}return it->second;
}}"""
        ),
    ]


def _generate_deserialize_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the function to de-serialize the enumeration from a JSON value."""
    enum_name = cpp_naming.enum_name(enumeration.name)

    from_wstring = cpp_naming.function_name(
        Identifier(f"{enumeration.name}_from_wstring")
    )

    function_name = cpp_naming.function_name(
        Identifier(f"deserialize_{enumeration.name}")
    )

    return Stripped(
        f"""\
std::pair<
{I}common::optional<types::{enum_name}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}const nlohmann::json& json
) {{
{I}return DeserializeEnumeration<types::{enum_name}>(
{II}json,
{II}wstringification::{from_wstring},
{II}L"{enum_name}"
{I});
}}"""
    )


@require(lambda cls: len(cls.concrete_descendants) > 0)
def _generate_dispatch_deserialize_definition(cls: intermediate.ClassUnion) -> Stripped:
    """Generate the def. of the dispatching deserialization function for ``cls``."""
    interface_name = cpp_naming.interface_name(cls.name)

    function_name = cpp_naming.function_name(Identifier(f"deserialize_{cls.name}"))

    return Stripped(
        f"""\
/**
 * \\brief Dispatch the deserialization for an instance
 * of types::{interface_name}.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return the deserialized instance, or an error, if any
 */
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
);"""
    )


@require(lambda named_union: len(named_union.implementers) > 0)
def _generate_dispatch_deserialize_definition_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the def. of the dispatching deserialization function for a union."""
    union_name = cpp_naming.union_name(named_union.name)

    function_name = cpp_naming.function_name(
        Identifier(f"deserialize_{named_union.name}")
    )

    return Stripped(
        f"""\
/**
 * \\brief Dispatch the deserialization for an instance
 * of types::{union_name}.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return the deserialized instance, or an error, if any
 */
std::pair<
{I}common::optional<types::{union_name}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
);"""
    )


def _determine_deserialize_function_for_class(
    cls: intermediate.ClassUnion,
) -> Stripped:
    """
    Determine the function to be called to de-serialize an instance of ``cls``.

    The result includes also template parameters, if any are necessary.
    """
    deserialize_name = cpp_naming.function_name(Identifier(f"Deserialize_{cls.name}"))

    interface_name = cpp_naming.interface_name(cls.name)

    if len(cls.concrete_descendants) == 0:
        if len(cls.ancestors) == 0:
            deserialize_function = Stripped(deserialize_name)
        else:
            deserialize_function = Stripped(
                f"""\
{deserialize_name}<
{I}types::{interface_name}
>"""
            )
    else:
        deserialize_function = Stripped(deserialize_name)

    return deserialize_function


def _deserialize_expr_for_atomic_item(
    item_type_anno: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """Generate the expression of the callable to de-serialize a tuple item."""
    items_primitive_type = intermediate.try_primitive_type(item_type_anno)

    if items_primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_DESERIALIZE[items_primitive_type]

    if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("This case should have been handled before.")

    elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
        if isinstance(item_type_anno.our_type, intermediate.Enumeration):
            return cpp_naming.function_name(
                Identifier(f"deserialize_{item_type_anno.our_type.name}")
            )

        elif isinstance(item_type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(
            item_type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            deserialize_cls = _determine_deserialize_function_for_class(
                cls=item_type_anno.our_type
            )

            return Stripped(
                f"""\
[&additional_properties](const nlohmann::json& a_json) {{
{I}return {deserialize_cls}(a_json, additional_properties);
}}"""
            )

        elif isinstance(item_type_anno.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is not part of the class hierarchy, so there is no
            # ancestor to upcast to -- the dispatching function is always called
            # bare, without any template parameter.
            deserialize_cls = cpp_naming.function_name(
                Identifier(f"Deserialize_{item_type_anno.our_type.name}")
            )

            return Stripped(
                f"""\
[&additional_properties](const nlohmann::json& a_json) {{
{I}return {deserialize_cls}(a_json, additional_properties);
}}"""
            )

        else:
            # noinspection PyTypeChecker
            assert_never(item_type_anno.our_type)

    elif isinstance(
        item_type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return _json_deserialize_function_for(item_type_anno)

    else:
        # noinspection PyTypeChecker
        assert_never(item_type_anno)

    raise AssertionError("Should not have gotten here")


def _generate_no_instance_and_error_factories() -> List[Stripped]:
    """Generate the factories of a failed de-serialization."""
    return [
        Stripped(
            f"""\
/**
 * \\brief Give out a failed de-serialization with \\p cause as its message.
 *
 * \\tparam T type of the value which could not be de-serialized
 * \\param cause human-readable description of the failure
 * \\return no value, and the error
 */
template <typename T>
std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> NoInstanceAndDeserializationErrorWithCause(
{I}std::wstring cause
) {{
{I}return std::make_pair<
{II}common::optional<T>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}std::move(cause)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Give out a failed de-serialization with \\p error.
 *
 * \\tparam T type of the value which could not be de-serialized
 * \\param error of the de-serialization
 * \\return no value, and the error
 */
template <typename T>
std::pair<
{I}common::optional<T>,
{I}common::optional<DeserializationError>
> NoInstanceAndDeserializationError(
{I}DeserializationError error
) {{
{I}return std::make_pair<
{II}common::optional<T>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}std::move(error)
{II})
{I});
}}"""
        ),
    ]


def _generate_parse_into() -> Stripped:
    """Generate the function to assign the result of a parse to a target variable."""
    return Stripped(
        f"""\
/**
 * \\brief Assign the value parsed to \\p target, or give out the error of the parse.
 *
 * We deliberately take the *result* of a parse instead of the JSON value and
 * the function which parses it. The item parsers of a tuple vary both in number
 * and in type, so no signature taking the parser could serve every parse;
 * taking the result lets this single function serve all of them.
 *
 * \\param target variable to be assigned the value parsed
 * \\param parsed result of the parse
 * \\return the error, if the parse failed
 */
template <typename T>
common::optional<DeserializationError> ParseInto(
{I}common::optional<T>& target,
{I}std::pair<
{II}common::optional<T>,
{II}common::optional<DeserializationError>
{I}>&& parsed
) {{
{I}if (parsed.second.has_value()) {{
{II}return std::move(parsed.second);
{I}}}

{I}target = std::move(parsed.first);

{I}return common::nullopt;
}}"""
    )


def _generate_parse_properties() -> Stripped:
    """Generate the generic function to parse the properties of an instance."""
    return Stripped(
        f"""\
/**
 * \\brief Parse the properties of an instance from \\p json.
 *
 * This function factors out everything which the property loop of a class does
 * not say about the class it belongs to: walking the keys, looking the property
 * up, refusing or accepting an unknown one and marking the property on
 * the error path. The class itself supplies only \\p on_property, which
 * dispatches on the property and assigns the local variables that its
 * constructor is finally called with.
 *
 * NOTE (mristin):
 * We walk the keys which are actually there, instead of asking for each
 * property of the class whether it is there. An instance carries only a few of
 * the many properties which a class declares, and nlohmann's object is
 * a ``std::map``, so asking costs a tree walk per property -- twice over, as
 * the value then has to be fetched. Walking also detects an unknown key on
 * the way, which is why there is no separate pass for that.
 *
 * NOTE (mristin):
 * We take \\p map_of_properties in, instead of letting \\p on_property work on
 * the JSON name of the property, because we want the class to dispatch with
 * a hard-wired ``switch`` whose branches assign the local variables of
 * the caller.
 *
 * A ``switch`` needs an integral constant, and C++ can not switch on a string,
 * so the name has to be translated into a literal of the property enumeration
 * first. We do that here rather than in the class so that the translation, and
 * the error reported when the name matches no property at all, are written
 * once instead of once per class.
 *
 * \\param json object whose properties are to be parsed
 * \\param map_of_properties maps the JSON name of a property to its literal
 * \\param additional_properties if not set, refuse a key which matches
 * no property
 * \\param on_property parses the value of the recognized property
 * \\return the error, if the parsing failed
 */
template <typename EnumT, typename OnPropertyT>
common::optional<DeserializationError> ParseProperties(
{I}const nlohmann::json& json,
{I}const std::unordered_map<std::string, EnumT>& map_of_properties,
{I}bool additional_properties,
{I}const OnPropertyT& on_property
) {{
{I}#ifdef DEBUG
{I}if (!json.is_object()) {{
{II}throw std::logic_error(
{III}"Unexpected non-object in ParseProperties. "
{III}"ParseProperties expects the caller to have checked that."
{II});
{I}}}
{I}#endif

{I}for (const auto& key_val : json.items()) {{
{II}auto it(
{III}map_of_properties.find(key_val.key())
{II});

{II}if (it == map_of_properties.end()) {{
{III}if (additional_properties) {{
{IIII}continue;
{III}}}

{III}return DeserializationError(
{IIII}common::Concat(
{IIIII}L"Unexpected additional property: ",
{IIIII}common::Utf8ToWstring(key_val.key())
{IIII})
{III});
{II}}}

{II}common::optional<DeserializationError> error(
{III}on_property(it->second, key_val.value())
{II});

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<PropertySegment>(
{IIIII}common::Utf8ToWstring(key_val.key())
{IIII})
{III});

{III}return error;
{II}}}
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_check_model_type() -> Stripped:
    """Generate the function verifying the model type of an instance."""
    return Stripped(
        f"""\
/**
 * \\brief Check that \\p json is an object whose model type is \\p expected.
 *
 * The model type is compared as the string which came on the wire. That refuses
 * a value of the wrong type just as well as parsing it would, and costs neither
 * a conversion to a wide string nor the allocation which goes with it.
 *
 * \\param json value expected to be an object carrying a model type
 * \\param expected model type of the class
 * \\return the error, if \\p json does not bear \\p expected
 */
common::optional<DeserializationError> CheckModelType(
{I}const nlohmann::json& json,
{I}const char* expected
) {{
{I}const std::string* model_type;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}model_type,
{II}error
{I}) = GetModelTypeFrom(json);

{I}if (error.has_value()) {{
{II}return error;
{I}}}

{I}if (*model_type != expected) {{
{II}return DeserializationError(
{III}common::Concat(
{IIII}L"Expected model type '",
{IIII}common::Utf8ToWstring(expected),
{IIII}L"', but got: ",
{IIII}common::Utf8ToWstring(*model_type)
{III})
{II});
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_check_json_object() -> Stripped:
    """Generate the function checking that a JSON value is an object."""
    return Stripped(
        f"""\
/**
 * \\brief Check that \\p json is a JSON object.
 *
 * \\param json value to be checked
 * \\return the error, if \\p json is anything else
 */
common::optional<DeserializationError> CheckJsonObject(
{I}const nlohmann::json& json
) {{
{I}if (!json.is_object()) {{
{II}return DeserializationError(
{III}common::Concat(
{IIII}L"Expected an object, but got: ",
{IIII}common::Utf8ToWstring(json.type_name())
{III})
{II});
{I}}}

{I}return common::nullopt;
}}"""
    )


def _generate_property_enums_and_maps(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """
    Generate a property enumeration per class and its mapping from the JSON names.

    ``ParseProperties`` switches on a literal, and C++ can not switch on a string,
    so the JSON name of a property has to be translated into one first.
    """
    result = [
        Stripped("namespace properties {"),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        enum_name = cpp_naming.enum_name(Identifier(f"Of_{cls.name}"))

        literals = [
            cpp_naming.enum_literal_name(prop.name) for prop in cls.properties
        ]  # type: List[str]

        if cls.serialization.with_model_type:
            assert all(prop.json_name != "modelType" for prop in cls.properties), (
                f"Expected no property of {cls.name!r} to be serialized as "
                f"'modelType', as the class carries the discriminator of that name, "
                f"but at least one is"
            )

            literals.append(_MODEL_TYPE_LITERAL)

        literals_joined = ",\n".join(literals)

        if len(literals) == 0:
            result.append(
                Stripped(
                    f"""\
enum class {enum_name} : std::uint32_t {{
}};  // enum class {enum_name}"""
                )
            )
        else:
            result.append(
                Stripped(
                    f"""\
enum class {enum_name} : std::uint32_t {{
{I}{indent_but_first_line(literals_joined, I)}
}};  // enum class {enum_name}"""
                )
            )

    for cls in symbol_table.concrete_classes:
        enum_name = cpp_naming.enum_name(Identifier(f"Of_{cls.name}"))

        map_name = cpp_naming.constant_name(Identifier(f"map_of_{cls.name}"))

        items = []  # type: List[Stripped]

        for prop in cls.properties:
            items.append(
                Stripped(
                    f"""\
{{
{I}{cpp_common.string_literal(prop.json_name)},
{I}{enum_name}::{cpp_naming.enum_literal_name(prop.name)}
}}"""
                )
            )

        if cls.serialization.with_model_type:
            items.append(
                Stripped(
                    f"""\
{{
{I}"modelType",
{I}{enum_name}::{_MODEL_TYPE_LITERAL}
}}"""
                )
            )

        items_joined = ",\n".join(items)

        if len(items) == 0:
            result.append(
                Stripped(
                    f"""\
const std::unordered_map<
{I}std::string,
{I}{enum_name}
> {map_name};"""
                )
            )
        else:
            result.append(
                Stripped(
                    f"""\
const std::unordered_map<
{I}std::string,
{I}{enum_name}
> {map_name} = {{
{I}{indent_but_first_line(items_joined, I)}
}};"""
                )
            )

    result.append(Stripped("}  // namespace properties"))

    return result


def _generate_unexpected_property_literal_error() -> Stripped:
    """Generate the factory for the error thrown on an out-of-range literal."""
    return Stripped(
        f"""\
/**
 * \\brief Create the exception to be thrown on an unexpected property literal.
 *
 * Every ``switch`` over the properties of a class covers all the literals of
 * its enumeration, so we can only get here if the value has been corrupted.
 * We report that as a logic error, and not as a de-serialization error, since
 * it does not originate in the input.
 *
 * \\param enum_name name of the property enumeration, for the message
 * \\param property the unexpected literal
 * \\return the exception to be thrown
 */
template <typename EnumT>
std::logic_error UnexpectedPropertyLiteralError(
{I}const char* enum_name,
{I}EnumT property
) {{
{I}return std::logic_error(
{II}common::Concat(
{III}"Unexpected properties literal of ",
{III}enum_name,
{III}": ",
{III}std::to_string(
{IIII}static_cast<std::uint32_t>(property)
{III})
{II})
{I});
}}"""
    )


def _json_parse_item_expr(
    item_type_anno: intermediate.AtomicTypeAnnotation,
) -> Tuple[Stripped, bool]:
    """
    Determine the parser of an item of a list, and whether it takes the options.

    A class and a named union are parsed with ``additional_properties`` handed
    down to them, everything else without, which is why ``DeserializeList`` has
    an overload for each.
    """
    items_primitive_type = intermediate.try_primitive_type(item_type_anno)

    if items_primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_DESERIALIZE[items_primitive_type], False

    if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("This case should have been handled before.")

    elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
        if isinstance(item_type_anno.our_type, intermediate.Enumeration):
            return (
                Stripped(
                    cpp_naming.function_name(
                        Identifier(f"deserialize_{item_type_anno.our_type.name}")
                    )
                ),
                False,
            )

        elif isinstance(item_type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(
            item_type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            return (
                _determine_deserialize_function_for_class(cls=item_type_anno.our_type),
                True,
            )

        elif isinstance(item_type_anno.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is not part of the class hierarchy, so there is no
            # ancestor to upcast to -- the dispatching function is always called
            # bare, without any template parameter.
            return (
                Stripped(
                    cpp_naming.function_name(
                        Identifier(f"Deserialize_{item_type_anno.our_type.name}")
                    )
                ),
                True,
            )

        else:
            # noinspection PyTypeChecker
            assert_never(item_type_anno.our_type)

    elif isinstance(
        item_type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return _json_deserialize_function_for(item_type_anno), False

    else:
        # noinspection PyTypeChecker
        assert_never(item_type_anno)

    raise AssertionError("Should not have gotten here")


def _json_parse_expr(prop: intermediate.Property) -> Stripped:
    """
    Generate the expression parsing the value of the given property.

    The expression evaluates to a pair of the optional value and the optional
    error, which :py:func:`_generate_parse_properties_of_cls` hands over to
    ``ParseInto``.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    primitive_type = intermediate.try_primitive_type(type_anno)

    if primitive_type is not None:
        return Stripped(f"{_PRIMITIVE_TYPE_TO_DESERIALIZE[primitive_type]}(value)")

    deserialize_function: Stripped

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("This case should have been handled before.")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            deserialize_function = cpp_naming.function_name(
                Identifier(f"deserialize_{type_anno.our_type.name}")
            )

            return Stripped(f"{deserialize_function}(value)")

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(
            type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            deserialize_function = _determine_deserialize_function_for_class(
                cls=type_anno.our_type
            )

            return Stripped(
                f"""\
{deserialize_function}(
{I}value,
{I}additional_properties
)"""
            )

        elif isinstance(type_anno.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is not part of the class hierarchy, so there is no
            # ancestor to upcast to -- the dispatching function is always called
            # bare, without any template parameter.
            deserialize_function = cpp_naming.function_name(
                Identifier(f"Deserialize_{type_anno.our_type.name}")
            )

            return Stripped(
                f"""\
{deserialize_function}(
{I}value,
{I}additional_properties
)"""
            )

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            "List items are restricted to atomic types (primitives, "
            "constrained primitives, classes, enumerations and JSON-able values), "
            "so no nested optionals, lists or tuples are expected here."
        )

        item_type = cpp_common.generate_type(
            type_anno.items, types_namespace=cpp_common.TYPES_NAMESPACE
        )

        parse_item, takes_options = _json_parse_item_expr(type_anno.items)

        arguments = [Stripped("value")]
        if takes_options:
            arguments.append(Stripped("additional_properties"))
        arguments.append(parse_item)

        arguments_joined = ",\n".join(arguments)

        return Stripped(
            f"""\
DeserializeList<
{I}{indent_but_first_line(item_type, I)}
>(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_types = []  # type: List[Stripped]
        item_exprs = []  # type: List[Stripped]

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
                cpp_common.generate_type(
                    item_type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
                )
            )
            item_exprs.append(_deserialize_expr_for_atomic_item(item_type_anno))

        item_types_joined = ",\n".join(item_types)
        item_exprs_joined = ",\n".join(item_exprs)

        function_name = f"DeserializeTuple{len(type_anno.items)}"

        return Stripped(
            f"""\
{function_name}<
{I}{indent_but_first_line(item_types_joined, I)}
>(
{I}value,
{I}{indent_but_first_line(item_exprs_joined, I)}
)"""
        )

    elif isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        deserialize_function = _json_deserialize_function_for(type_anno)

        return Stripped(f"{deserialize_function}(value)")

    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)

    raise AssertionError("Should not have gotten here")


def _cls_template_prefix(cls: intermediate.ClassUnion, with_default: bool) -> Stripped:
    """
    Generate the signature prefix of a function de-serializing an instance of ``cls``.

    A class with ancestors is de-serialized through a template, so that
    a dispatcher can give out a pointer to the ancestor it was asked for without
    an upcast. ``with_default`` tells whether the default of the SFINAE
    parameter is spelled out, which it is in the declaration and not in
    the definition.
    """
    interface_name = cpp_naming.interface_name(cls.name)

    if len(cls.ancestors) == 0:
        return Stripped(
            f"""\
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
>"""
        )

    default = " = nullptr" if with_default else ""

    return Stripped(
        f"""\
template <
{I}typename T,
{I}typename std::enable_if<
{II}std::is_base_of<T, types::{interface_name}>::value
{I}>::type*{default}
>
std::pair<
{I}common::optional<std::shared_ptr<T> >,
{I}common::optional<DeserializationError>
>"""
    )


def _cls_ok_type(cls: intermediate.ClassUnion) -> Stripped:
    """
    Determine the type of the pointee given out for an instance of ``cls``.

    We have to distinguish between the cases where we directly create an upcast
    pointer to an ancestor class, and the cases where there are no ancestors.
    """
    if len(cls.ancestors) == 0:
        return Stripped(f"types::{cpp_naming.interface_name(cls.name)}")

    return Stripped("T")


def _generate_parse_properties_of_cls_definition(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the def. of the function parsing the properties of ``cls``."""
    interface_name = cpp_naming.interface_name(cls.name)

    function_name = cpp_naming.function_name(
        Identifier(f"parse_properties_of_{cls.name}")
    )

    return Stripped(
        f"""\
/**
 * \\brief Parse the properties of an instance of types::{interface_name}.
 *
 * The model type, if the class carries one, is expected to have been verified
 * by the caller, which is what lets a dispatcher avoid verifying it twice.
 *
 * \\param json object whose properties are to be parsed
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return the de-serialized instance, or an error, if any
 */
{_cls_template_prefix(cls, with_default=True)} {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
);"""
    )


def _generate_parse_properties_of_cls_implementation(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the impl. of the function parsing the properties of ``cls``."""
    class_name = cpp_naming.class_name(cls.name)
    enum_name = cpp_naming.enum_name(Identifier(f"Of_{cls.name}"))
    map_name = cpp_naming.constant_name(Identifier(f"map_of_{cls.name}"))

    ok_type = _cls_ok_type(cls)

    blocks = []  # type: List[Stripped]

    # region The locals which the constructor is finally called with
    if len(cls.properties) > 0:
        init_statements = []  # type: List[Stripped]

        for prop in cls.properties:
            var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
            var_type = cpp_common.generate_type(
                type_annotation=prop.type_annotation,
                types_namespace=cpp_common.TYPES_NAMESPACE,
            )

            if not isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ):
                if "\n" in var_type:
                    var_type = Stripped(
                        f"""\
common::optional<
{I}{indent_but_first_line(var_type, I)}
>"""
                    )
                elif var_type.endswith(">"):
                    var_type = Stripped(f"common::optional<{var_type} >")
                else:
                    var_type = Stripped(f"common::optional<{var_type}>")

            init_statements.append(Stripped(f"{var_type} {var_name};"))

        blocks.append(Stripped("\n\n".join(init_statements)))
    # endregion

    # region The property loop
    case_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        literal_name = cpp_naming.enum_literal_name(prop.name)
        var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

        parse_expr = _json_parse_expr(prop)

        case_blocks.append(
            Stripped(
                f"""\
case properties::{enum_name}::{literal_name}:
{I}return ParseInto(
{II}{var_name},
{II}{indent_but_first_line(parse_expr, II)}
{I});"""
            )
        )

    if cls.serialization.with_model_type:
        case_blocks.append(
            Stripped(
                f"""\
case properties::{enum_name}::{_MODEL_TYPE_LITERAL}:
{I}// NOTE (mristin):
{I}// The model type has been verified before the loop, so there is nothing
{I}// left to do with it here.
{I}return common::nullopt;"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw UnexpectedPropertyLiteralError(
{II}"properties::{enum_name}",
{II}property
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    # NOTE (mristin):
    # A class with no properties at all never looks at the value of the key,
    # and only the discriminator can bring it here, so we leave the parameter
    # unnamed rather than let it warn.
    value_parameter = (
        "const nlohmann::json& value"
        if len(cls.properties) > 0
        else "const nlohmann::json&"
    )

    blocks.append(
        Stripped(
            f"""\
common::optional<DeserializationError> error(
{I}ParseProperties(
{II}json,
{II}properties::{map_name},
{II}additional_properties,
{II}[&](
{III}properties::{enum_name} property,
{III}{value_parameter}
{II}) -> common::optional<DeserializationError> {{
{III}switch (property) {{
{IIII}{indent_but_first_line(case_blocks_joined, IIII)}
{III}}}
{II}}}
{I})
);

if (error.has_value()) {{
{I}return NoInstanceAndDeserializationError<
{II}std::shared_ptr<{ok_type}>
{I}>(
{II}std::move(*error)
{I});
}}"""
        )
    )
    # endregion

    # region The required properties
    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

        blocks.append(
            Stripped(
                f"""\
if (!{var_name}.has_value()) {{
{I}return NoInstanceAndDeserializationErrorWithCause<
{II}std::shared_ptr<{ok_type}>
{I}>(
{II}L"The required property {prop.json_name} is missing"
{I});
}}"""
            )
        )
    # endregion

    # region The construction
    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
            set(prop.name for prop in cls.properties)
            == set(arg.name for arg in cls.constructor.arguments)
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    constructor_args = []  # type: List[Stripped]
    for arg in cls.constructor.arguments:
        prop = cls.properties_by_name[arg.name]

        var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            constructor_args.append(Stripped(f"std::move({var_name})"))
        else:
            constructor_args.append(Stripped(f"std::move(*{var_name})"))

    constructor_args_joined = ",\n".join(constructor_args)

    if len(constructor_args) == 0:
        construction = Stripped(f"new types::{class_name}()")
    else:
        construction = Stripped(
            f"""\
new types::{class_name}(
{I}{indent_but_first_line(constructor_args_joined, I)}
)"""
        )

    blocks.append(
        Stripped(
            f"""\
return std::make_pair(
{I}common::make_optional<
{II}std::shared_ptr<{ok_type}>
{I}>(
{II}// NOTE (mristin):
{II}// We deliberately do not use std::make_shared here to avoid an unnecessary
{II}// upcast.
{II}{indent_but_first_line(construction, II)}
{I}),
{I}common::nullopt
);"""
        )
    )
    # endregion

    function_name = cpp_naming.function_name(
        Identifier(f"parse_properties_of_{cls.name}")
    )

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
{_cls_template_prefix(cls, with_default=False)} {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_deserialize_cls_definition(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the def. of the checking, non-dispatching ``Deserialize*``."""
    interface_name = cpp_naming.interface_name(cls.name)

    function_name = cpp_naming.function_name(Identifier(f"deserialize_{cls.name}"))

    return Stripped(
        f"""\
/**
 * \\brief Deserialize \\p json to an instance of types::{interface_name}.
 *
 * No dispatch is performed. The model type, if the class carries one, is
 * verified here, since the caller has not read it.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return the de-serialized instance, or an error, if any
 */
{_cls_template_prefix(cls, with_default=True)} {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
);"""
    )


def _generate_deserialize_cls_implementation(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the impl. of the checking, non-dispatching ``Deserialize*``."""
    function_name = cpp_naming.function_name(Identifier(f"deserialize_{cls.name}"))

    parse_properties_name = cpp_naming.function_name(
        Identifier(f"parse_properties_of_{cls.name}")
    )

    ok_type = _cls_ok_type(cls)

    if cls.serialization.with_model_type:
        # NOTE (mristin):
        # ``CheckModelType`` establishes that the JSON value is an object as
        # well, since it has to look the model type up in it.
        check = Stripped(
            f"""\
common::optional<DeserializationError> error(
{I}CheckModelType(
{II}json,
{II}{cpp_common.string_literal(naming.json_model_type(cls.name))}
{I})
);"""
        )
    else:
        check = Stripped(
            f"""\
common::optional<DeserializationError> error(
{I}CheckJsonObject(json)
);"""
        )

    call = Stripped(f"{parse_properties_name}(json, additional_properties)")
    if len(cls.ancestors) > 0:
        call = Stripped(
            f"""\
{parse_properties_name}<T>(
{I}json,
{I}additional_properties
)"""
        )

    return Stripped(
        f"""\
{_cls_template_prefix(cls, with_default=False)} {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
) {{
{I}{indent_but_first_line(check, I)}

{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<{ok_type}>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}return {indent_but_first_line(call, I)};
}}"""
    )


def _generate_deserialize_from() -> Stripped:
    """Generate the generic function behind every public ``*From``."""
    return Stripped(
        f"""\
/**
 * \\brief De-serialize \\p json and render the outcome as an expected value.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\param deserialize de-serializes the value
 * \\return the de-serialized value, or the error
 */
template <typename T, typename DeserializeT>
common::expected<
{I}T,
{I}DeserializationError
> DeserializeFrom(
{I}const nlohmann::json& json,
{I}bool additional_properties,
{I}const DeserializeT& deserialize
) {{
{I}common::optional<T> instance;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}instance,
{II}error
{I}) = deserialize(json, additional_properties);

{I}if (instance.has_value()) {{
{II}return std::move(*instance);
{I}}}

{I}if (!error.has_value()) {{
{II}throw std::logic_error(
{III}"Unexpected null error when null instance."
{II});
{I}}}

{I}return common::make_unexpected(
{II}std::move(*error)
{I});
}}"""
    )


def _generate_deserialize_enumeration_generic() -> Stripped:
    """Generate the generic function to de-serialize an enumeration literal."""
    return Stripped(
        f"""\
/**
 * \\brief De-serialize a literal of an enumeration from \\p json.
 *
 * \\p from_wstring is a template argument taken by reference, so the call is
 * statically bound and nothing is paid for the genericity.
 *
 * \\tparam EnumT enumeration to be de-serialized
 * \\param json value expected to be the text of a literal
 * \\param from_wstring maps the text to a literal, if it is one
 * \\param enum_name name of the enumeration, for the message
 * \\return the literal, or an error, if any
 */
template <typename EnumT, typename FromWstringT>
std::pair<
{I}common::optional<EnumT>,
{I}common::optional<DeserializationError>
> DeserializeEnumeration(
{I}const nlohmann::json& json,
{I}const FromWstringT& from_wstring,
{I}const wchar_t* enum_name
) {{
{I}common::optional<std::wstring> text;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}text,
{II}error
{I}) = DeserializeWstring(json);

{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<EnumT>(
{III}std::move(*error)
{II});
{I}}}

{I}common::optional<EnumT> literal(
{II}from_wstring(*text)
{I});

{I}if (!literal.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<EnumT>(
{III}common::Concat(
{IIII}L"Invalid literal for ",
{IIII}enum_name,
{IIII}L": ",
{IIII}*text
{III})
{II});
{I}}}

{I}return std::make_pair(
{II}std::move(literal),
{II}common::nullopt
{I});
}}"""
    )


@require(
    lambda cls: len(cls.concrete_descendants) > 0,
    "No dispatch possible without concrete descendants",
)
def _generate_dispatch_deserialize_implementation(
    cls: intermediate.ClassUnion,
) -> List[Stripped]:
    """
    Generate the impl. of the dispatching deserialization function for ``cls``.

    We convert the JSON ``modelType`` string to a ``types::ModelType`` via the
    single, file-wide ``ModelTypeFromModelTypeString`` lookup (see
    :py:func:`_generate_model_type_string_to_model_type`) and then ``switch``
    on it -- mirroring how the XML side dispatches
    (``model_type_from_element_name`` + a per-interface ``switch`` in
    ``_generate_class_from_element``) -- instead of routing through a
    ``std::map<std::string, std::function<...>>`` built fresh for every
    abstract class. This lets us abort immediately either because the model
    type is not recognized at all (the global lookup fails) or because it is
    recognized but is not one of this interface's own concrete descendants
    (the ``switch`` falls through to ``default``), without any runtime
    indirection through ``std::function``.
    """
    targets: Iterable[intermediate.ConcreteClass]

    if isinstance(cls, intermediate.ConcreteClass):
        targets = itertools.chain([cls], cls.concrete_descendants)
    else:
        targets = cls.concrete_descendants

    assert targets is not None

    interface_name = cpp_naming.interface_name(cls.name)

    case_blocks = []  # type: List[Stripped]
    for target_cls in targets:
        literal_name = cpp_naming.enum_literal_name(target_cls.name)

        # NOTE (mristin):
        # We have read the model type in order to dispatch at all, and
        # the ``case`` we are in is precisely the one it named, so we go
        # straight to the property loop instead of through
        # ``Deserialize{Cls}``, which would verify the model type a second
        # time.
        target_function = cpp_naming.function_name(
            Identifier(f"parse_properties_of_{target_cls.name}")
        )

        if len(target_cls.ancestors) > 0:
            # NOTE (mristin):
            # ``target_function`` is only templated if ``target_cls`` itself
            # has ancestors -- true for every proper descendant (which always
            # has ``cls`` among its ancestors), but *not* necessarily true when
            # ``target_cls`` is ``cls`` itself (a concrete-with-descendants
            # class dispatching itself, with no meta-model ancestors of its
            # own), so we must not add the template argument unconditionally.
            call = Stripped(
                f"""\
{target_function}<
{I}types::{interface_name}
>"""
            )
        else:
            call = Stripped(target_function)

        case_blocks.append(
            Stripped(
                f"""\
case types::ModelType::{literal_name}:
{I}return {indent_but_first_line(call, I)}(json, additional_properties);"""
            )
        )

    case_blocks_joined = "\n".join(case_blocks)

    function_name = cpp_naming.function_name(Identifier(f"deserialize_{cls.name}"))

    return [
        Stripped(
            f"""\
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
) {{
{I}const std::string* model_type_str;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}model_type_str,
{II}error
{I}) = GetModelTypeFrom(json);

{I}if (error.has_value()) {{
{II}return NoInstanceAndDeserializationError<
{III}std::shared_ptr<types::{interface_name}>
{II}>(
{III}std::move(*error)
{II});
{I}}}

{I}common::optional<types::ModelType> model_type(
{II}ModelTypeFromModelTypeString(*model_type_str)
{I});

{I}if (!model_type.has_value()) {{
{II}return NoInstanceAndDeserializationErrorWithCause<
{III}std::shared_ptr<types::{interface_name}>
{II}>(
{III}common::Concat(
{IIII}L"The model type does not correspond to any known class: ",
{IIII}common::Utf8ToWstring(*model_type_str)
{III})
{II});
{I}}}

{I}switch (*model_type) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{II}default:
{III}return NoInstanceAndDeserializationErrorWithCause<
{IIII}std::shared_ptr<types::{interface_name}>
{III}>(
{IIII}common::Concat(
{IIIII}L"The dispatch to the JSON de-serialization of "
{IIIII}L"types::{interface_name} "
{IIIII}L"is not defined for model type: ",
{IIIII}common::Utf8ToWstring(*model_type_str)
{IIII})
{III});
{I}}}
}}"""
        ),
    ]


def _generate_wrap_deserialized_as_variant_function() -> Stripped:
    """
    Generate the generic helper to wrap a de-serialized pointer as a variant.

    Every implementer of a named union is de-serialized through its own
    canonical entry point (bypassing the union), and the resulting pointer
    then needs to be wrapped into the union's ``common::variant`` alternative
    of the implementer's most specific root. As the roots may overlap, the
    alternative is picked explicitly by its index instead of relying on
    the implicit conversion into the variant.
    This shape is identical for every implementer of every union (only the
    types differ), so we factor it out into a single generic function
    instead of unrolling it at each dispatch case, mirroring how
    ``DeserializeTupleN``/``SerializeTupleN`` factor out the per-item
    boilerplate for tuples.
    """
    return Stripped(
        f"""\
/**
 * \\brief Wrap a de-serialized pointer as a named union's variant alternative.
 *
 * Every implementer of a named union is de-serialized through its own
 * canonical entry point (bypassing the union), and the resulting pointer
 * then needs to be wrapped into the union's common::variant alternative
 * of the implementer's most specific root. As the roots may overlap,
 * the alternative is picked explicitly by its index \\p Index.
 *
 * \\param result the result of a de-serialization call for one implementer
 * \\return the result wrapped as a variant, or the propagated error
 */
template <typename VariantT, std::size_t Index, typename T>
std::pair<
{I}common::optional<VariantT>,
{I}common::optional<DeserializationError>
> WrapDeserializedAsVariant(
{I}std::pair<
{II}common::optional<std::shared_ptr<T> >,
{II}common::optional<DeserializationError>
{I}> result
) {{
{I}if (result.first.has_value()) {{
{II}return std::make_pair<
{III}common::optional<VariantT>,
{III}common::optional<DeserializationError>
{II}>(
{III}VariantT(
{IIII}common::in_place_index_t<Index>(),
{IIII}std::move(*result.first)
{III}),
{III}common::nullopt
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<VariantT>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(result.second)
{I});
}}"""
    )


def _generate_deserialize_and_wrap_snippet_for_named_union_implementer(
    target_cls: intermediate.ConcreteClass, named_union: intermediate.NamedUnion
) -> Stripped:
    """
    Generate the snippet to de-serialize a single implementer and wrap it.

    The resulting ``pair<optional<shared_ptr<T>>, ...>`` is wrapped into
    the union's ``common::variant`` in one call via
    :py:func:`_generate_wrap_deserialized_as_variant_function`.

    We go straight to the property loop. The union has checked that the JSON
    value is an object, and it has either matched the model type of
    the implementer or picked the implementer structurally, in which case
    the implementer carries no model type at all -- so there is nothing left
    for ``Deserialize{Cls}`` to check.
    """
    union_name = cpp_naming.union_name(named_union.name)

    # NOTE (mristin):
    # The alternatives of the variant follow the roots, see
    # :py:func:`cpp_common.generate_named_union_variant_definition`.
    root = named_union.most_specific_root_of(target_cls)
    root_index = next(i for i, a_root in enumerate(named_union.roots) if a_root is root)

    target_function = cpp_naming.function_name(
        Identifier(f"parse_properties_of_{target_cls.name}")
    )

    target_interface_name = cpp_naming.interface_name(target_cls.name)

    call: Stripped
    if len(target_cls.ancestors) > 0:
        # NOTE (mristin):
        # We request the class's own interface explicitly so that we always
        # obtain ``shared_ptr<types::{target_interface_name}>`` back,
        # regardless of the union we are dispatching for.
        call = Stripped(
            f"""\
{target_function}<
{I}types::{target_interface_name}
>"""
        )
    else:
        call = Stripped(target_function)

    return Stripped(
        f"""\
return WrapDeserializedAsVariant<
{I}types::{union_name},
{I}{root_index}
>(
{I}{indent_but_first_line(call, I)}(
{II}json,
{II}additional_properties
{I})
);"""
    )


@require(lambda named_union: len(named_union.implementers) > 0)
def _generate_dispatch_deserialize_implementation_for_named_union(
    named_union: intermediate.NamedUnion,
) -> List[Stripped]:
    """
    Generate the impl. of the dispatching deserialization function for a union.

    Every flattened implementer is de-serialized either by ``modelType`` (if
    it is marked with :attr:`~intermediate.Serialization.with_model_type`) or
    -- for the remaining implementers -- structurally, by checking which
    implementer's required properties are all present in the JSON object.
    :py:func:`aas_core_codegen.intermediate._translate._verify_named_unions_are_dispatchable_in_json`
    already ascertained that these two groups are unambiguous, so we do not
    have to double-check disjointness here.
    """
    union_name = cpp_naming.union_name(named_union.name)
    function_name = cpp_naming.function_name(
        Identifier(f"deserialize_{named_union.name}")
    )

    implementers_with_model_type = []  # type: List[intermediate.ConcreteClass]
    implementers_without_model_type = []  # type: List[intermediate.ConcreteClass]
    for implementer in named_union.implementers:
        if implementer.serialization.with_model_type:
            implementers_with_model_type.append(implementer)
        else:
            implementers_without_model_type.append(implementer)

    body_blocks = [
        Stripped(
            f"""\
common::optional<DeserializationError> not_an_object(
{I}CheckJsonObject(json)
);

if (not_an_object.has_value()) {{
{I}return NoInstanceAndDeserializationError<
{II}types::{union_name}
{I}>(
{II}std::move(*not_an_object)
{I});
}}"""
        )
    ]  # type: List[Stripped]

    if len(implementers_with_model_type) > 0:
        case_blocks = []  # type: List[Stripped]
        for target_cls in implementers_with_model_type:
            literal_name = cpp_naming.enum_literal_name(target_cls.name)
            snippet = (
                _generate_deserialize_and_wrap_snippet_for_named_union_implementer(
                    target_cls=target_cls, named_union=named_union
                )
            )

            case_blocks.append(
                Stripped(
                    f"""\
case types::ModelType::{literal_name}: {{
{I}{indent_but_first_line(snippet, I)}
}}"""
                )
            )

        case_blocks_joined = "\n".join(case_blocks)

        body_blocks.append(
            Stripped(
                f"""\
if (json.contains("modelType")) {{
{I}const std::string* model_type_str;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}model_type_str,
{II}error
{I}) = GetModelTypeFrom(json);

{I}if (error.has_value()) {{
{II}return std::make_pair<
{III}common::optional<types::{union_name}>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}std::move(error)
{II});
{I}}}

{I}common::optional<types::ModelType> model_type(
{II}ModelTypeFromModelTypeString(*model_type_str)
{I});

{I}if (!model_type.has_value()) {{
{II}std::wstring message = common::Concat(
{III}L"The model type does not correspond to any known class: ",
{III}common::Utf8ToWstring(*model_type_str)
{II});

{II}return std::make_pair<
{III}common::optional<types::{union_name}>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}switch (*model_type) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{II}default: {{
{III}std::wstring message = common::Concat(
{IIII}L"The dispatch to the JSON de-serialization of "
{IIII}L"types::{union_name} "
{IIII}L"is not defined for model type: ",
{IIII}common::Utf8ToWstring(*model_type_str)
{III});

{III}return std::make_pair<
{IIII}common::optional<types::{union_name}>,
{IIII}common::optional<DeserializationError>
{III}>(
{IIII}common::nullopt,
{IIII}common::make_optional<DeserializationError>(
{IIIII}message
{IIII})
{III});
{II}}}
{I}}}
}}"""
            )
        )

    for target_cls in implementers_without_model_type:
        required_properties = [
            prop
            for prop in target_cls.properties
            if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        ]
        assert len(required_properties) > 0, (
            f"Expected at least one required property for the structurally "
            f"dispatched implementer {target_cls.name!r} of "
            f"the named union {named_union.name!r}, as this should have been "
            f"verified in the intermediate representation."
        )

        condition = " &&\n".join(
            f"json.contains({cpp_common.string_literal(prop.json_name)})"
            for prop in required_properties
        )

        snippet = _generate_deserialize_and_wrap_snippet_for_named_union_implementer(
            target_cls=target_cls, named_union=named_union
        )

        body_blocks.append(
            Stripped(
                f"""\
if ({indent_but_first_line(condition, I)}) {{
{I}{indent_but_first_line(snippet, I)}
}}"""
            )
        )

    body_blocks.append(
        Stripped(
            f"""\
std::wstring message(
{I}L"Could not determine a concrete type to dispatch the JSON "
{I}L"de-serialization of types::{union_name} to, based neither "
{I}L"on the modelType nor on the required properties present "
{I}L"in the object"
);

return std::make_pair<
{I}common::optional<types::{union_name}>,
{I}common::optional<DeserializationError>
>(
{I}common::nullopt,
{I}common::make_optional<DeserializationError>(
{II}message
{I})
);"""
        )
    )

    body_blocks_joined = "\n\n".join(body_blocks)

    return [
        Stripped(
            f"""\
std::pair<
{I}common::optional<types::{union_name}>,
{I}common::optional<DeserializationError>
> {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
) {{
{I}{indent_but_first_line(body_blocks_joined, I)}
}}"""
        )
    ]


def _render_deserialization_implementation(
    deserialize_function: Stripped,
    value_type: Stripped,
    deserialization_name: Identifier,
) -> Stripped:
    """Render the implementation of the ``*From`` function."""
    return Stripped(
        f"""\
common::expected<
{I}{indent_but_first_line(value_type, I)},
{I}DeserializationError
> {deserialization_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
) {{
{I}return DeserializeFrom<
{II}{indent_but_first_line(value_type, II)}
{I}>(
{II}json,
{II}additional_properties,
{II}{indent_but_first_line(deserialize_function, II)}
{I});
}}"""
    )


def _generate_deserialization_implementation(
    cls: intermediate.ClassUnion,
) -> Stripped:
    """Generate the implementation of ``*From`` function."""
    deserialize_function = _determine_deserialize_function_for_class(cls=cls)

    value_type = Stripped(
        f"std::shared_ptr<types::{cpp_naming.interface_name(cls.name)}>"
    )

    deserialization_name = cpp_naming.function_name(Identifier(f"{cls.name}_from"))

    return _render_deserialization_implementation(
        deserialize_function=deserialize_function,
        value_type=value_type,
        deserialization_name=deserialization_name,
    )


def _generate_deserialization_implementation_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the implementation of ``*From`` function for a named union."""
    # NOTE (mristin):
    # A named union is not part of the class hierarchy, so there is no ancestor
    # to upcast to -- the dispatching function is always called bare, without any
    # template parameter.
    deserialize_function = Stripped(
        cpp_naming.function_name(Identifier(f"Deserialize_{named_union.name}"))
    )

    value_type = Stripped(f"types::{cpp_naming.union_name(named_union.name)}")

    deserialization_name = cpp_naming.function_name(
        Identifier(f"{named_union.name}_from")
    )

    return _render_deserialization_implementation(
        deserialize_function=deserialize_function,
        value_type=value_type,
        deserialization_name=deserialization_name,
    )


def _generate_serialization_exception_implementation() -> List[Stripped]:
    """Generate the implementation of the ``SerializationException``."""
    return [
        Stripped("// region SerializationException"),
        Stripped(
            f"""\
std::string RenderSerializationErrorMessage(
{I}const std::wstring& cause,
{I}const iteration::Path& path
) {{
{I}return common::WstringToUtf8(
{II}common::Concat(
{III}L"Serialization failed at ",
{III}path.ToWstring(),
{III}L": ",
{III}cause
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
SerializationException::SerializationException(
{I}std::wstring cause,
{I}iteration::Path path
) :
{I}cause_(std::move(cause)),
{I}path_(std::move(path)),
{I}msg_(RenderSerializationErrorMessage(cause, path)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
const char* SerializationException::what() const noexcept {{
{I}return msg_.c_str();
}}"""
        ),
        Stripped(
            f"""\
const std::wstring& SerializationException::cause() const noexcept {{
{I}return cause_;
}}"""
        ),
        Stripped(
            f"""\
const iteration::Path& SerializationException::path() const noexcept {{
{I}return path_;
}}"""
        ),
        Stripped("// endregion SerializationException"),
    ]


def _generate_serialize_int() -> Stripped:
    """Generate the function to serialize an integer to a JSON value."""
    return Stripped(
        f"""\
/**
 * \\brief Serialize the given number to a JSON value.
 *
 * We verify that the integer is within the range representable by 64-bit floats
 * for interoperability with other de-serializers.
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeInt64(int64_t value) {{
{I}if (
{II}value < -9007199254740991L
{II}|| value > 9007199254740991L
{I}) {{
{II}const std::wstring message = common::Concat(
{III}L"The integer ",
{III}std::to_wstring(value),
{III}L" can not be serialized to JSON "
{III}L"as it is outside the range [-2^53 + 1, 2^53 - 1] and can not "
{III}L"be exactly represented as a 64-bit floating point number."
{II});

{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<SerializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<SerializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>(
{II}common::make_optional<nlohmann::json>(value),
{II}common::nullopt
{I});
}}"""
    )


def _generate_serialize_bool() -> Stripped:
    """
    Generate the function to serialize a boolean to a JSON value.

    Named to match ``DeserializeBool``, even though converting a C++ ``bool``
    to a JSON value can not actually fail.
    """
    return Stripped(
        f"""\
/**
 * Serialize the given boolean to a JSON value.
 */
nlohmann::json SerializeBool(
{I}bool value
) {{
{I}return value;
}}"""
    )


def _generate_serialize_double() -> Stripped:
    """Generate the function to serialize a double to a JSON value."""
    return Stripped(
        f"""\
/**
 * \\brief Serialize the given floating-point number to a JSON value.
 *
 * JSON knows neither an infinity nor a not-a-number, so we refuse to serialize
 * them instead of silently writing them out as ``null``.
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeDouble(double value) {{
{I}if (!std::isfinite(value)) {{
{II}const std::wstring message = common::Concat(
{III}L"The floating-point number ",
{III}std::to_wstring(value),
{III}L" can not be serialized to JSON as JSON knows no infinity "
{III}L"and no not-a-number."
{II});

{II}return std::make_pair<
{III}common::optional<nlohmann::json>,
{III}common::optional<SerializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<SerializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>(
{II}common::make_optional<nlohmann::json>(value),
{II}common::nullopt
{I});
}}"""
    )


def _generate_serialize_str() -> Stripped:
    """Generate the function to serialize a wide string to a JSON value."""
    return Stripped(
        f"""\
/**
 * Serialize the given text to a JSON value.
 */
nlohmann::json SerializeWstring(
{I}const std::wstring& text
) {{
{I}return nlohmann::json(
{II}common::WstringToUtf8(text)
{I});
}}"""
    )


def _generate_serialize_bytearray() -> Stripped:
    """Generate the function to serialize a byte array to a JSON value."""
    return Stripped(
        f"""\
/**
 * Serialize the given bytes to a JSON value.
 */
nlohmann::json SerializeByteArray(
{I}const std::vector<std::uint8_t>& bytes
) {{
{I}return nlohmann::json(
{II}stringification::Base64Encode(bytes)
{I});
}}"""
    )


_PRIMITIVE_TYPE_TO_SERIALIZE = {
    intermediate.PrimitiveType.BOOL: Stripped("SerializeBool"),
    intermediate.PrimitiveType.INT: Stripped("SerializeInt64"),
    intermediate.PrimitiveType.FLOAT: Stripped("SerializeDouble"),
    intermediate.PrimitiveType.STR: Stripped("SerializeWstring"),
    intermediate.PrimitiveType.BYTEARRAY: Stripped("stringification::Base64Encode"),
}
assert all(
    primitive_type in _PRIMITIVE_TYPE_TO_SERIALIZE
    for primitive_type in intermediate.PrimitiveType
)


def _generate_serialize_list_with_fallible_item_serialization() -> Stripped:
    """Generate a function to serialize a list with fallible item serialization."""
    return Stripped(
        f"""\
/**
 * Serialize the given list to a JSON array where item serialization might fail.
 */
template<typename T, typename FallibleSerializeItemT>
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeListWithFallible(
{I}const std::vector<T>& list,
{I}FallibleSerializeItemT&& fallible_serialize_item
) {{
{I}nlohmann::json serialized = nlohmann::json::array();

{I}serialized.get_ptr<nlohmann::json::array_t*>()->reserve(
{II}list.size()
{I});

{I}size_t index = 0;

{I}for (const T& item : list) {{
{II}common::optional<nlohmann::json> json_item;
{II}common::optional<SerializationError> error;

{II}std::tie(
{III}json_item,
{III}error
{II}) = fallible_serialize_item(item);

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(
{IIIII}index
{IIII})
{III});

{III}return std::make_pair<
{IIII}common::optional<nlohmann::json>,
{IIII}common::optional<SerializationError>
{III}>(
{IIII}common::nullopt,
{IIII}std::move(error)
{III});
{II}}}

{II}serialized.emplace_back(
{III}std::move(*json_item)
{II});

{II}++index;
{I}}}

{I}return std::make_pair(
{II}std::move(serialized),
{II}common::nullopt
{I});
}}"""
    )


def _generate_serialize_list_with_infallible_item_serialization() -> Stripped:
    """Generate a function to serialize a list with infallible item serialization."""
    return Stripped(
        f"""\
/**
 * Serialize the given list to a JSON array where item serialization can not fail.
 */
template<typename T, typename InfallibleSerializeItemT>
nlohmann::json SerializeListWithInfallible(
{I}const std::vector<T>& list,
{I}InfallibleSerializeItemT&& infallible_serialize_item
) {{
{I}nlohmann::json serialized = nlohmann::json::array();

{I}serialized.get_ptr<nlohmann::json::array_t*>()->reserve(
{II}list.size()
{I});

{I}for (const T& item : list) {{
{II}serialized.emplace_back(
{III}infallible_serialize_item(item)
{II});
{I}}}

{I}return serialized;
}}"""
    )


def _generate_serialize_tuple_function(arity: int) -> Stripped:
    """
    Generate a generic function to serialize a tuple of the given ``arity``.

    Each positional item is serialized by its own ``serialize_item{i}``
    callable, in whichever shape that item's own serialization has. ``AsFallible``
    lifts the ones which can not fail, so the items of a tuple need no
    normalizing lambda per kind at the call site.
    """
    assert arity > 0

    template_params_joined = ",\n".join(
        [f"typename T{i}" for i in range(arity)]
        + [f"typename SerializeItemT{i}" for i in range(arity)]
    )

    item_types_joined = ",\n".join(f"T{i}" for i in range(arity))

    parameters = ",\n".join(
        f"SerializeItemT{i}&& serialize_item{i}" for i in range(arity)
    )

    item_stmts = []  # type: List[Stripped]
    for i in range(arity):
        item_stmts.append(
            Stripped(
                f"""\
common::optional<nlohmann::json> json_item{i};
std::tie(
{I}json_item{i},
{I}error
) = AsFallible(
{I}serialize_item{i}(
{II}Deref(std::get<{i}>(value))
{I})
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::IndexSegment>(
{III}{i}
{II})
{I});
{I}return std::make_pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}

serialized.emplace_back(
{I}std::move(*json_item{i})
);"""
            )
        )

    item_stmts_joined = "\n\n".join(item_stmts)

    function_name = f"SerializeTuple{arity}"

    return Stripped(
        f"""\
/**
 * Serialize a tuple of {arity} item(s) to a JSON array.
 */
template <
{I}{indent_but_first_line(template_params_joined, I)}
>
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> {function_name}(
{I}const std::tuple<
{II}{indent_but_first_line(item_types_joined, II)}
{I}>& value,
{I}{indent_but_first_line(parameters, I)}
) {{
{I}nlohmann::json serialized = nlohmann::json::array();
{I}serialized.get_ptr<nlohmann::json::array_t*>()->reserve(
{II}{arity}
{I});

{I}common::optional<SerializationError> error;

{I}{indent_but_first_line(item_stmts_joined, I)}

{I}return std::make_pair(
{II}std::move(serialized),
{II}common::nullopt
{I});
}}"""
    )


def _generate_no_json_and_error_factories() -> List[Stripped]:
    """Generate the factories of a failed serialization."""
    return [
        Stripped(
            f"""\
/**
 * \\brief Give out a failed serialization with \\p cause as its message.
 *
 * \\param cause human-readable description of the failure
 * \\return no value, and the error
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> NoJsonAndSerializationErrorWithCause(
{I}std::wstring cause
) {{
{I}return std::make_pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<SerializationError>(
{III}std::move(cause)
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Give out a failed serialization with \\p error.
 *
 * \\param error of the serialization
 * \\return no value, and the error
 */
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> NoJsonAndSerializationError(
{I}SerializationError error
) {{
{I}return std::make_pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<SerializationError>(
{III}std::move(error)
{II})
{I});
}}"""
        ),
    ]


def _generate_serialize_into() -> Stripped:
    """Generate the function to put the result of a serialization under a key."""
    return Stripped(
        f"""\
/**
 * \\brief Put the value serialized under \\p key of \\p result, or give out
 * the error of the serialization, marked with \\p property.
 *
 * We deliberately take the *result* of a serialization instead of the value
 * and the function which serializes it. The item serializers of a tuple vary
 * both in number and in type, so no signature taking the serializer could
 * serve every serialization; taking the result lets this single function
 * serve all of them.
 *
 * \\param result object to be written to
 * \\param key of the property in the JSON object
 * \\param property which the key stands for, for the path of the error
 * \\param serialized result of the serialization
 * \\return the error, if the serialization failed
 */
common::optional<SerializationError> SerializeInto(
{I}nlohmann::json& result,
{I}const char* key,
{I}iteration::Property property,
{I}std::pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>&& serialized
) {{
{I}if (serialized.second.has_value()) {{
{II}serialized.second->path.segments.emplace_front(
{III}common::make_unique<iteration::PropertySegment>(property)
{II});

{II}return std::move(serialized.second);
{I}}}

{I}result[key] = std::move(*serialized.first);

{I}return common::nullopt;
}}"""
    )


def _serialization_is_fallible(
    type_annotation: intermediate.TypeAnnotationUnion,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> bool:
    """
    Check whether the serialization of a value of ``type_annotation`` can fail.

    A number is the only value we may have to refuse: JSON holds neither an
    infinity nor a not-a-number, and an integer only within
    [-2^53 + 1, 2^53 - 1]. Everything else goes as it comes -- an enumeration
    literal is written as its text, and a string, a boolean and a byte array
    are written verbatim -- so a serializer can fail exactly where a number is
    reachable from what it serializes.

    The ``ids_of_fallible_types`` comes from
    :py:func:`_collect_ids_of_types_with_fallible_serialization`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    a_type = intermediate.try_primitive_type(type_anno)
    if a_type is not None:
        return (
            a_type is intermediate.PrimitiveType.INT
            or a_type is intermediate.PrimitiveType.FLOAT
        )

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return _serialization_is_fallible(type_anno.items, ids_of_fallible_types)

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # One ``SerializeTuple{N}`` serves every tuple of that arity, and those
        # differ in whether their items can fail, so it has a single shape and
        # that shape has to be the fallible one. A tuple of items which can not
        # fail therefore carries a check which can not fire -- the one place
        # where we pay for something which can not happen, and it costs a tuple
        # property a branch.
        return True

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # An enumeration is a leaf here -- a literal is not a number -- and every
        # other one of our types is reported by the fixed point.
        return intermediate.runtime_id(type_anno.our_type) in ids_of_fallible_types

    if isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # A JSON-able value is shaped only at run time, so we have to assume that
        # it holds a number. This is the one place where the analysis approximates,
        # and it errs on the side of the number being there: a JSON-able value
        # carrying an infinity is exactly what we have to refuse.
        return True

    return False


def _serialization_dispatches(cls: intermediate.ClassUnion) -> bool:
    """Check whether the run-time type of an instance of ``cls`` is open."""
    return len(cls.concrete_descendants) > 0 or isinstance(
        cls, intermediate.AbstractClass
    )


def _own_serialization_is_fallible(
    cls: intermediate.ConcreteClass,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> bool:
    """
    Check whether serializing an instance of exactly ``cls`` can fail.

    Unlike the entry of ``cls`` in ``ids_of_fallible_types``, this disregards
    the descendants, as it concerns only the serializer which is not dispatched.
    """
    return any(
        _serialization_is_fallible(prop.type_annotation, ids_of_fallible_types)
        for prop in cls.properties
    )


def _collect_ids_of_types_with_fallible_serialization(
    symbol_table: intermediate.SymbolTable,
) -> Set[intermediate.IdOfOurType]:
    """
    Collect the IDs of our types whose serialization can fail.

    This is a fixed point, as the classes refer to each other and a cycle must
    not be walked twice. The set handed to :py:func:`_serialization_is_fallible`
    is the one being built, so it answers only for the types already in it, which
    is all the fixed point needs and is why it grows until nothing changes.
    """
    result = set()  # type: Set[intermediate.IdOfOurType]

    changed = True
    while changed:
        changed = False

        for cls in symbol_table.classes:
            if intermediate.runtime_id(cls) in result:
                continue

            if any(
                _serialization_is_fallible(prop.type_annotation, result)
                for prop in cls.properties
            ) or any(
                intermediate.runtime_id(descendant) in result
                for descendant in cls.concrete_descendants
            ):
                result.add(intermediate.runtime_id(cls))
                changed = True

        for union in symbol_table.named_unions:
            if intermediate.runtime_id(union) in result:
                continue

            # NOTE (mristin):
            # A root is serialized by its own serializer, which dispatches over
            # the root's concrete classes if its run-time type is open, so
            # a union can fail exactly where one of its roots can.
            if any(intermediate.runtime_id(root) in result for root in union.roots):
                result.add(intermediate.runtime_id(union))
                changed = True

    return result


def _determine_serialize_function_for_class(
    cls: intermediate.ClassUnion,
) -> Stripped:
    """
    Determine the function which serializes an instance of ``cls``.

    The run-time type of a value is open only where the declared type leaves it
    open -- an abstract class, or a concrete class with concrete descendants --
    and only there does ``Serialize{Cls}`` dispatch, and only over the concrete
    classes of ``cls`` (see :py:func:`_generate_dispatching_serialize_cls`).
    Hence the serializer can fail exactly where ``cls`` can, as the fixed point
    in :py:func:`_collect_ids_of_types_with_fallible_serialization` decides.
    Everywhere else the declared type already answers which serializer to call,
    and we pay neither the ``model_type()`` nor the ``switch`` nor
    the ``dynamic_cast``.
    """
    return Stripped(cpp_naming.function_name(Identifier(f"serialize_{cls.name}")))


def _concrete_serialize_function_name(cls: intermediate.ConcreteClass) -> Identifier:
    """
    Determine the name of the serializer of exactly ``cls``, without dispatch.

    If ``cls`` has concrete descendants, ``Serialize{Cls}`` dispatches, so
    the serializer of exactly ``cls`` needs a name of its own.
    """
    if len(cls.concrete_descendants) > 0:
        return cpp_naming.function_name(Identifier(f"serialize_concrete_{cls.name}"))

    return cpp_naming.function_name(Identifier(f"serialize_{cls.name}"))


def _serialize_item_expr(
    item_type_anno: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """
    Generate the expression of the serializer of an item of a list or a tuple.

    An instance is held as a ``std::shared_ptr``, and the serializer takes
    the instance, so somebody has to dereference it. A list is homogeneous, so
    ``SerializeListOfInstancesWith*`` knows to; a tuple is not, so
    ``SerializeTuple{N}`` asks ``Deref`` per item. Either way there is nothing
    left to do here.
    """
    items_primitive_type = intermediate.try_primitive_type(item_type_anno)

    if items_primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_SERIALIZE[items_primitive_type]

    if isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Expected this case to be handled before")

    elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
        if isinstance(item_type_anno.our_type, intermediate.Enumeration):
            enum_name = cpp_naming.enum_name(item_type_anno.our_type.name)

            return Stripped(f"SerializeEnumeration<types::{enum_name}>")

        elif isinstance(item_type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Expected this case to be handled before")

        elif isinstance(
            item_type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            return _determine_serialize_function_for_class(item_type_anno.our_type)

        elif isinstance(item_type_anno.our_type, intermediate.NamedUnion):
            union_name = cpp_naming.union_name(item_type_anno.our_type.name)
            return Stripped(f"Serialize{union_name}")

        else:
            # noinspection PyTypeChecker
            assert_never(item_type_anno.our_type)

    elif isinstance(
        item_type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return _json_serialize_function_for(item_type_anno)

    else:
        # noinspection PyTypeChecker
        assert_never(item_type_anno)

    raise AssertionError("Should not have gotten here")


def _serialize_value_expr(
    type_anno: intermediate.TypeAnnotationUnion,
    value_expr: Stripped,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """
    Generate the expression serializing ``value_expr`` of the ``type_anno``.

    The expression evaluates to a ``nlohmann::json`` if the serialization can
    not fail, and to the pair of the optional value and the optional error if
    it can -- which
    :py:func:`_serialization_is_fallible` decides for the very same
    ``type_anno``.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)

    if primitive_type is not None:
        serialize_function = _PRIMITIVE_TYPE_TO_SERIALIZE[primitive_type]

        return Stripped(
            f"""\
{serialize_function}(
{I}{indent_but_first_line(value_expr, I)}
)"""
        )

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Expected this case to be handled before")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            return Stripped(
                f"""\
SerializeEnumeration(
{I}{indent_but_first_line(value_expr, I)}
)"""
            )

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Expected this case to be handled before")

        elif isinstance(
            type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            serialize_function = _determine_serialize_function_for_class(
                type_anno.our_type
            )

            return Stripped(
                f"""\
{serialize_function}(
{I}*({indent_but_first_line(value_expr, I)})
)"""
            )

        elif isinstance(type_anno.our_type, intermediate.NamedUnion):
            union_name = cpp_naming.union_name(type_anno.our_type.name)

            return Stripped(
                f"""\
Serialize{union_name}(
{I}{indent_but_first_line(value_expr, I)}
)"""
            )

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple), (
            "List items are restricted to atomic types (primitives, "
            "constrained primitives, classes, enumerations and JSON-able values), "
            "so no nested optionals, lists or tuples are expected here."
        )

        # NOTE (mristin):
        # A list of instances holds pointers, so it is served by the functions
        # which dereference an item; everything else holds the value itself.
        of_instances = isinstance(
            type_anno.items, intermediate.OurTypeAnnotation
        ) and isinstance(
            type_anno.items.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        )

        if _serialization_is_fallible(type_anno.items, ids_of_fallible_types):
            serialize_list = (
                "SerializeListOfInstancesWithFallible"
                if of_instances
                else "SerializeListWithFallible"
            )
        else:
            serialize_list = (
                "SerializeListOfInstancesWithInfallible"
                if of_instances
                else "SerializeListWithInfallible"
            )

        serialize_item = _serialize_item_expr(type_anno.items)

        return Stripped(
            f"""\
{serialize_list}(
{I}{indent_but_first_line(value_expr, I)},
{I}{indent_but_first_line(serialize_item, I)}
)"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_exprs = []  # type: List[Stripped]

        for item_type_anno in type_anno.items:
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            item_exprs.append(_serialize_item_expr(item_type_anno))

        item_exprs_joined = ",\n".join(item_exprs)

        function_name = f"SerializeTuple{len(type_anno.items)}"

        return Stripped(
            f"""\
{function_name}(
{I}{indent_but_first_line(value_expr, I)},
{I}{indent_but_first_line(item_exprs_joined, I)}
)"""
        )

    elif isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        serialize_function = _json_serialize_function_for(type_anno)

        return Stripped(
            f"""\
{serialize_function}(
{I}{indent_but_first_line(value_expr, I)}
)"""
        )

    elif isinstance(type_anno, intermediate.OptionalTypeAnnotation):
        raise AssertionError(
            f"Expected the optional to have been stripped by the caller, "
            f"but got: {type_anno}"
        )

    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)

    raise AssertionError("Should not have gotten here")


def _generate_serialize_property(
    prop: intermediate.Property,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """Generate the statements which serialize the property ``prop``."""
    getter = cpp_naming.getter_name(prop.name)

    value_expr: Stripped
    maybe_var = None  # type: Optional[Identifier]

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        maybe_var = cpp_naming.variable_name(Identifier(f"maybe_{prop.name}"))
        value_expr = Stripped(f"*{maybe_var}")
    else:
        value_expr = Stripped(f"that.{getter}()")

    type_anno = intermediate.beneath_optional(prop.type_annotation)

    serialize_expr = _serialize_value_expr(
        type_anno=type_anno,
        value_expr=value_expr,
        ids_of_fallible_types=ids_of_fallible_types,
    )

    json_prop_name_literal = cpp_common.string_literal(prop.json_name)

    code: Stripped

    if _serialization_is_fallible(type_anno, ids_of_fallible_types):
        prop_literal = cpp_naming.enum_literal_name(prop.name)

        code = Stripped(
            f"""\
error = SerializeInto(
{I}result,
{I}{json_prop_name_literal},
{I}iteration::Property::{prop_literal},
{I}{indent_but_first_line(serialize_expr, I)}
);
if (error.has_value()) {{
{I}return NoJsonAndSerializationError(
{II}std::move(*error)
{I});
}}"""
        )
    else:
        code = Stripped(
            f"""\
result[{json_prop_name_literal}] = {indent_but_first_line(serialize_expr, "")};"""
        )

    if maybe_var is not None:
        maybe_var_type = cpp_common.generate_type_with_const_ref_if_applicable(
            type_annotation=prop.type_annotation,
            types_namespace=cpp_common.TYPES_NAMESPACE,
        )

        # NOTE (mristin):
        # We test the binding rather than the getter. The getter is virtual, so
        # calling it a second time here would double its cost for every optional
        # property of every instance.
        code = Stripped(
            f"""\
{maybe_var_type} {maybe_var}(
{I}that.{getter}()
);
if ({maybe_var}.has_value()) {{
{I}{indent_but_first_line(code, I)}
}}"""
        )

    return code


def _serialize_cls_return_type(fallible: bool) -> Stripped:
    """
    Generate the return type of a serializer.

    A serializer which can not fail gives the JSON value out plainly, so that
    neither it nor its caller carries an error which could never be set.
    """
    if not fallible:
        return Stripped("nlohmann::json")

    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
>"""
    )


def _generate_serialize_cls(
    cls: intermediate.ConcreteClass,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """Generate the serialization function for exactly the class ``cls``."""
    fallible = _own_serialization_is_fallible(cls, ids_of_fallible_types)

    blocks = [
        Stripped("nlohmann::json result = nlohmann::json::object();")
    ]  # type: List[Stripped]

    if fallible:
        blocks.append(Stripped("common::optional<SerializationError> error;"))

    for prop in cls.properties:
        blocks.append(
            _generate_serialize_property(
                prop=prop,
                ids_of_fallible_types=ids_of_fallible_types,
            )
        )

    if cls.serialization.with_model_type:
        model_type_literal = cpp_common.string_literal(naming.json_model_type(cls.name))
        blocks.append(Stripped(f'result["modelType"] = {model_type_literal};'))

    if fallible:
        blocks.append(
            Stripped(
                f"""\
return std::make_pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
>(
{I}common::make_optional<nlohmann::json>(std::move(result)),
{I}common::nullopt
);"""
            )
        )
    else:
        blocks.append(Stripped("return result;"))

    blocks_joined = "\n\n".join(blocks)

    serialize_name = _concrete_serialize_function_name(cls)

    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
{_serialize_cls_return_type(fallible)} {serialize_name}(
{I}const types::{interface_name}& that
) {{
{I}{indent_but_first_line(blocks_joined, I)}
}}"""
    )


def _generate_deref() -> Stripped:
    """Generate the dereference of a pointer item of a tuple."""
    return Stripped(
        f"""\
/**
 * \\brief Give out the instance behind \\p pointer.
 *
 * The items of a tuple are heterogeneous, so ``SerializeTuple{{N}}`` can not
 * know which of them are instances -- held as a ``std::shared_ptr`` -- and
 * which are values. It asks per item instead, and this is the answer for
 * a pointer. See the overload for everything else.
 */
template <typename T>
const T& Deref(const std::shared_ptr<T>& pointer) {{
{I}return *pointer;
}}"""
    )


def _generate_deref_identity() -> Stripped:
    """Generate the pass-through of a non-pointer item of a tuple."""
    return Stripped(
        f"""\
/**
 * @copybrief Deref
 *
 * The item is the value itself, so there is nothing to dereference.
 */
template <typename T>
const T& Deref(const T& value) {{
{I}return value;
}}"""
    )


def _generate_serialize_enumeration() -> Stripped:
    """
    Generate the one function which serializes a literal of any enumeration.

    ``stringification::to_string`` is an overload set of plain functions, one
    per enumeration, so it can not be named where a serializer is expected:
    the serializer is a template parameter there, and without a target type
    there is nothing for the overload resolution to go on. Inside a template
    the call is dependent on ``EnumT``, so it is resolved once that is known --
    which is why one function serves every enumeration, and a call site which
    has to name a serializer names the specialization it wants.
    """
    return Stripped(
        f"""\
/**
 * Serialize the literal \\p that of an enumeration to a JSON value.
 *
 * \\param that literal to be serialized
 * \\return the JSON value
 */
template <typename EnumT>
nlohmann::json SerializeEnumeration(
{I}const EnumT& that
) {{
{I}return stringification::to_string(that);
}}"""
    )


def _generate_as_fallible() -> Stripped:
    """Generate the lifting of an infallible serialization into the fallible shape."""
    return Stripped(
        f"""\
/**
 * \\brief Give the value out in the shape of a serialization which can fail.
 *
 * ``SerializeTuple{{N}}`` takes one item serializer per item, and the items of
 * a tuple differ in kind, so some of them can fail and some of them can not.
 * Lifting the ones which can not is what lets the tuple treat all of them
 * alike, without a normalizing lambda per kind at the call site.
 */
template <typename T>
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> AsFallible(T&& value) {{
{I}return std::make_pair(
{II}common::make_optional<nlohmann::json>(std::forward<T>(value)),
{II}common::nullopt
{I});
}}"""
    )


def _generate_as_fallible_identity() -> Stripped:
    """Generate the overload of ``AsFallible`` for an already fallible result."""
    return Stripped(
        f"""\
/**
 * @copybrief AsFallible
 *
 * The serialization could already fail, so there is nothing to lift.
 */
inline std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> AsFallible(
{I}std::pair<
{II}common::optional<nlohmann::json>,
{II}common::optional<SerializationError>
{I}>&& serialized
) {{
{I}return std::move(serialized);
}}"""
    )


def _generate_serialize_list_of_instances_overloads() -> List[Stripped]:
    """
    Generate the list serializations which dereference a pointer item.

    A list of instances holds ``std::shared_ptr``, while its item serializer
    takes the instance, so the dereference belongs here rather than in
    a lambda at each of the call sites.

    These are named apart from ``SerializeListWith*`` rather than overloading
    them. The caller always knows whether its items are instances, so there is
    nothing for the overload resolution to decide, and a name says at the call
    site what an overload would leave to be worked out.
    """
    return [
        Stripped(
            f"""\
/**
 * Serialize the given list of instances to a JSON array where item
 * serialization might fail.
 *
 * The items are pointers, which we dereference for the item serializer.
 */
template<typename T, typename FallibleSerializeItemT>
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeListOfInstancesWithFallible(
{I}const std::vector<std::shared_ptr<T> >& list,
{I}FallibleSerializeItemT&& fallible_serialize_item
) {{
{I}nlohmann::json serialized = nlohmann::json::array();

{I}serialized.get_ptr<nlohmann::json::array_t*>()->reserve(
{II}list.size()
{I});

{I}size_t index = 0;

{I}for (const std::shared_ptr<T>& item : list) {{
{II}common::optional<nlohmann::json> json_item;
{II}common::optional<SerializationError> error;

{II}std::tie(
{III}json_item,
{III}error
{II}) = fallible_serialize_item(*item);

{II}if (error.has_value()) {{
{III}error->path.segments.emplace_front(
{IIII}common::make_unique<iteration::IndexSegment>(
{IIIII}index
{IIII})
{III});

{III}return std::make_pair<
{IIII}common::optional<nlohmann::json>,
{IIII}common::optional<SerializationError>
{III}>(
{IIII}common::nullopt,
{IIII}std::move(error)
{III});
{II}}}

{II}serialized.emplace_back(
{III}std::move(*json_item)
{II});

{II}++index;
{I}}}

{I}return std::make_pair(
{II}std::move(serialized),
{II}common::nullopt
{I});
}}"""
        ),
        Stripped(
            f"""\
/**
 * Serialize the given list of instances to a JSON array where item
 * serialization can not fail.
 *
 * The items are pointers, which we dereference for the item serializer.
 */
template<typename T, typename InfallibleSerializeItemT>
nlohmann::json SerializeListOfInstancesWithInfallible(
{I}const std::vector<std::shared_ptr<T> >& list,
{I}InfallibleSerializeItemT&& infallible_serialize_item
) {{
{I}nlohmann::json serialized = nlohmann::json::array();

{I}serialized.get_ptr<nlohmann::json::array_t*>()->reserve(
{II}list.size()
{I});

{I}for (const std::shared_ptr<T>& item : list) {{
{II}serialized.emplace_back(
{III}infallible_serialize_item(*item)
{II});
{I}}}

{I}return serialized;
}}"""
        ),
    ]


def _generate_serialize_cls_declaration(
    cls: intermediate.ConcreteClass,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """
    Generate the forward declaration of the serializer of ``cls``.

    A class names the serializer of every class it holds, and the classes are
    emitted in the order of the symbol table, so a serializer has to be
    declared before any of them can call it.
    """
    fallible = _own_serialization_is_fallible(cls, ids_of_fallible_types)

    serialize_name = _concrete_serialize_function_name(cls)

    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
/**
 * \\brief Serialize \\p that instance of types::{interface_name} to a JSON value.
 *
 * \\param that instance to be serialized
 * \\return the JSON value{" , or an error, if any" if fallible else ""}
 */
{_serialize_cls_return_type(fallible)} {serialize_name}(
{I}const types::{interface_name}& that
);"""
    )


def _generate_dispatching_serialize_cls_declaration(
    cls: intermediate.ClassUnion,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """Generate the forward declaration of the dispatching serializer of ``cls``."""
    fallible = intermediate.runtime_id(cls) in ids_of_fallible_types

    serialize_name = _determine_serialize_function_for_class(cls)

    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
/**
 * \\brief Serialize \\p that instance of types::{interface_name} to a JSON value,
 * dispatching on its model type.
 *
 * \\param that instance to be serialized
 * \\return the JSON value{" , or an error, if any" if fallible else ""}
 */
{_serialize_cls_return_type(fallible)} {serialize_name}(
{I}const types::{interface_name}& that
);"""
    )


def _generate_dispatching_serialize_cls(
    cls: intermediate.ClassUnion,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """
    Generate the serializer of ``cls`` which dispatches on the model type.

    Unlike ``SerializeIClass``, this dispatches only over the concrete classes
    of ``cls``, so that it can fail only where ``cls`` can, and does not take
    over the fallibility of the whole meta-model.
    """
    fallible = intermediate.runtime_id(cls) in ids_of_fallible_types

    concrete_classes = list(cls.concrete_descendants)
    if isinstance(cls, intermediate.ConcreteClass):
        concrete_classes.insert(0, cls)

    model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))

    case_blocks = []  # type: List[Stripped]
    for concrete_cls in concrete_classes:
        serialize_name = _concrete_serialize_function_name(concrete_cls)

        if concrete_cls is cls:
            call = Stripped(f"{serialize_name}(that)")
        else:
            concrete_interface_name = cpp_naming.interface_name(concrete_cls.name)

            call = Stripped(
                f"""\
{serialize_name}(
{I}dynamic_cast<const types::{concrete_interface_name}&>(that)
)"""
            )

        # NOTE (mristin):
        # The dispatch has to give out one shape for every class, so a class
        # whose serialization can not fail is lifted into the fallible one.
        if fallible and not _own_serialization_is_fallible(
            concrete_cls, ids_of_fallible_types
        ):
            call = Stripped(
                f"""\
AsFallible(
{I}{indent_but_first_line(call, I)}
)"""
            )

        model_type_literal = cpp_naming.enum_literal_name(concrete_cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}return {indent_but_first_line(call, I)};"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default: {{
{I}std::string message = common::Concat(
{II}"Unexpected model type: ",
{II}std::to_string(
{III}static_cast<std::uint32_t>(
{IIII}that.model_type()
{III})
{II})
{I});

{I}throw std::invalid_argument(message);
}}"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    dispatch_name = _determine_serialize_function_for_class(cls)

    interface_name = cpp_naming.interface_name(cls.name)

    return Stripped(
        f"""\
{_serialize_cls_return_type(fallible)} {dispatch_name}(
{I}const types::{interface_name}& that
) {{
{I}// NOTE (mristin):
{I}// The dynamic casts are necessary due to virtual inheritance. Otherwise,
{I}// we would have used static casts.

{I}switch (that.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
    )


def _generate_serialize_iclass_definition(fallible: bool) -> Stripped:
    """Generate the definition of the main dispatch for serializing ``IClass``."""
    return Stripped(
        f"""\
/**
 * \\brief Serialize \\p that instance to a JSON value, dispatching on its
 * model type.
 *
 * \\param that instance to be serialized
 * \\return the JSON value{" , or an error, if any" if fallible else ""}
 */
{_serialize_cls_return_type(fallible)} SerializeIClass(
{I}const types::IClass& that
);"""
    )


def _generate_serialize_iclass_implementation(
    symbol_table: intermediate.SymbolTable,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """Generate the main dispatch function for serializing ``IClass``."""
    fallible = any(
        intermediate.runtime_id(cls) in ids_of_fallible_types
        for cls in symbol_table.concrete_classes
    )

    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        serialize_name = _concrete_serialize_function_name(cls)

        model_type_literal = cpp_naming.enum_literal_name(cls.name)
        model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))

        interface_name = cpp_naming.interface_name(cls.name)

        call = Stripped(
            f"""\
{serialize_name}(
{I}dynamic_cast<const types::{interface_name}&>(that)
)"""
        )

        # NOTE (mristin):
        # The dispatch has to give out one shape for every class, so a class
        # whose serialization can not fail is lifted into the fallible one.
        if fallible and not _own_serialization_is_fallible(cls, ids_of_fallible_types):
            call = Stripped(
                f"""\
AsFallible(
{I}{indent_but_first_line(call, I)}
)"""
            )

        case_blocks.append(
            Stripped(
                f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}return {indent_but_first_line(call, I)};"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default: {{
{I}std::string message = common::Concat(
{II}"Unexpected model type: ",
{II}std::to_string(
{III}static_cast<std::uint32_t>(
{IIII}that.model_type()
{III})
{II})
{I});

{I}throw std::invalid_argument(message);
}}"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
{_serialize_cls_return_type(fallible)} SerializeIClass(
{I}const types::IClass& that
) {{
{I}switch (that.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
    )


def _generate_serialize_implementation(fallible: bool) -> Stripped:
    """Generate the main serialization function."""
    if not fallible:
        return Stripped(
            f"""\
nlohmann::json Serialize(
{I}const types::IClass& that
) {{
{I}return SerializeIClass(that);
}}"""
        )

    return Stripped(
        f"""\
nlohmann::json Serialize(
{I}const types::IClass& that
) {{
{I}common::optional<nlohmann::json> result;
{I}common::optional<SerializationError> error;

{I}std::tie(
{II}result,
{II}error
{I}) = SerializeIClass(that);

{I}if (error.has_value()) {{
{II}throw SerializationException(
{III}std::move(error->cause),
{III}std::move(error->path)
{II});
{I}}}

{I}return std::move(*result);
}}"""
    )


def _named_union_serialization_is_fallible(
    named_union: intermediate.NamedUnion,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> bool:
    """
    Check whether the serialization of ``named_union`` can fail.

    A named union can fail exactly where one of its roots can, as
    the fixed point in :py:func:`_collect_ids_of_types_with_fallible_serialization`
    decides.
    """
    return intermediate.runtime_id(named_union) in ids_of_fallible_types


def _generate_serialize_named_union_declaration(
    named_union: intermediate.NamedUnion,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """
    Generate the forward declaration of a named union's ``Serialize`` function.

    We emit this once per union, before any class's own serialize
    implementation that might reference it by name -- otherwise a class with
    a union-typed property would call a not-yet-declared function.
    """
    fallible = _named_union_serialization_is_fallible(
        named_union, ids_of_fallible_types
    )

    union_name = cpp_naming.union_name(named_union.name)

    return Stripped(
        f"""\
{_serialize_cls_return_type(fallible)} Serialize{union_name}(
{I}const types::{union_name}& that
);"""
    )


@require(lambda named_union: len(named_union.roots) > 0)
def _generate_serialize_named_union_implementation(
    named_union: intermediate.NamedUnion,
    ids_of_fallible_types: Set[intermediate.IdOfOurType],
) -> Stripped:
    """
    Generate the function to serialize a named union, once per union.

    This switches on the ``common::variant``'s own ``index()`` -- the variant
    already knows which alternative, *i.e.*, which root it holds. Each root is
    serialized by its own serializer, which dispatches over the concrete classes
    of the root if its run-time type is open.
    """
    fallible = _named_union_serialization_is_fallible(
        named_union, ids_of_fallible_types
    )

    union_name = cpp_naming.union_name(named_union.name)

    case_blocks = []  # type: List[Stripped]
    for i, root in enumerate(named_union.roots):
        serialize_function = _determine_serialize_function_for_class(root)

        call = Stripped(f"{serialize_function}(*common::get<{i}>(that))")

        if fallible and intermediate.runtime_id(root) not in ids_of_fallible_types:
            call = Stripped(
                f"""\
AsFallible(
{I}{indent_but_first_line(call, I)}
)"""
            )

        case_blocks.append(
            Stripped(
                f"""\
case {i}:
{I}return {indent_but_first_line(call, I)};"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::logic_error(
{II}common::Concat(
{III}"Invalid variant index for {union_name}: ",
{III}std::to_string(that.index())
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
{_serialize_cls_return_type(fallible)} Serialize{union_name}(
{I}const types::{union_name}& that
) {{
{I}switch (that.index()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
    )


def _type_annotation_contains_list_of_instances(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> bool:
    """
    Check whether the type annotation holds a list of instances.

    Only such a list needs the ``SerializeListWith*`` overloads which
    dereference a ``std::shared_ptr`` item.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    if not isinstance(type_anno, intermediate.ListTypeAnnotation):
        return False

    if not isinstance(type_anno.items, intermediate.OurTypeAnnotation):
        return False

    return isinstance(
        type_anno.items.our_type,
        (intermediate.AbstractClass, intermediate.ConcreteClass),
    )


def _type_annotation_contains_list(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> bool:
    """Check whether the type annotation has a list type annotation."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        return True

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # Tuples are heterogeneous and fixed-length, so we never de-serialize them
        # with the generic ``DeserializeList``.
        return False

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _type_annotation_contains_list(type_annotation.value)

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        return False

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable,
    library_namespace: Stripped,
) -> str:
    """Generate implementation for JSON de/serialization."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.JSONIZATION_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/jsonization.hpp"
#include "{include_prefix_path}/stringification.hpp"
#include "{include_prefix_path}/wstringification.hpp"

#pragma warning(push, 0)
#include <cmath>
#include <set>
#include <sstream>
#include <unordered_map>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        *_generate_property_segment_implementation(),
        *_generate_index_segment_implementation(),
        *_generate_path_implementation(),
        Stripped("// region De-serialization"),
        *_generate_deserialization_error_implementation(),
        _generate_deserialize_bool(),
        _generate_deserialize_int(),
        _generate_deserialize_float(),
        _generate_deserialize_str(),
        _generate_deserialize_bytearray(),
        _generate_get_model_type(),
        *_generate_no_instance_and_error_factories(),
    ]

    if intermediate.uses_json_types(symbol_table):
        blocks.extend(
            [
                _generate_deserialize_json_value(),
                _generate_deserialize_json_array(),
                _generate_deserialize_json_object(),
            ]
        )

    if any(len(cls.concrete_descendants) > 0 for cls in symbol_table.classes) or any(
        implementer.serialization.with_model_type
        for named_union in symbol_table.named_unions
        for implementer in named_union.implementers
    ):
        blocks.extend(_generate_model_type_string_to_model_type(symbol_table))

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_wrap_deserialized_as_variant_function())

    if any(
        _type_annotation_contains_list(prop.type_annotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.append(_generate_deserialize_list())
        blocks.append(_generate_deserialize_list_of_instances())

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_deserialize_tuple_function(arity))

    if len(symbol_table.enumerations) > 0:
        blocks.append(_generate_deserialize_enumeration_generic())

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_deserialize_enumeration(enumeration))

    if len(symbol_table.concrete_classes) > 0:
        blocks.extend(_generate_property_enums_and_maps(symbol_table=symbol_table))
        blocks.append(_generate_unexpected_property_literal_error())
        blocks.append(_generate_parse_properties())
        blocks.append(_generate_check_json_object())

        if any(
            cls.serialization.with_model_type for cls in symbol_table.concrete_classes
        ):
            blocks.append(_generate_check_model_type())

    if any(len(cls.properties) > 0 for cls in symbol_table.concrete_classes):
        blocks.append(_generate_parse_into())

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(_generate_parse_properties_of_cls_definition(cls=cls))

            if len(cls.concrete_descendants) == 0:
                blocks.append(_generate_deserialize_cls_definition(cls=cls))

        if len(cls.concrete_descendants) > 0:
            blocks.append(_generate_dispatch_deserialize_definition(cls=cls))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_dispatch_deserialize_definition_for_named_union(
                named_union=named_union
            )
        )

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(_generate_parse_properties_of_cls_implementation(cls=cls))

            if len(cls.concrete_descendants) == 0:
                blocks.append(_generate_deserialize_cls_implementation(cls=cls))

        if len(cls.concrete_descendants) > 0:
            deserialize_dispatch_blocks = _generate_dispatch_deserialize_implementation(
                cls=cls
            )
            blocks.extend(deserialize_dispatch_blocks)

    for named_union in symbol_table.named_unions:
        blocks.extend(
            _generate_dispatch_deserialize_implementation_for_named_union(
                named_union=named_union
            )
        )

    blocks.append(_generate_deserialize_from())

    for cls in symbol_table.classes:
        blocks.append(_generate_deserialization_implementation(cls=cls))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_deserialization_implementation_for_named_union(
                named_union=named_union
            )
        )

    blocks.extend(
        [
            Stripped("// endregion De-serialization"),
            Stripped("// region Serialization"),
            Stripped(
                f"""\
/**
 * \\brief Represent a serialization error.
 *
 * We use this error internally to avoid unnecessary stack unwinding,
 * but throw the \\ref SerializationException at the final site of
 * the serialization for the user.
 */
struct SerializationError {{
{I}/**
{I} * Human-readable description of the error
{I} */
{I}std::wstring cause;

{I}/**
{I} * Path to the value that caused the error
{I} */
{I}iteration::Path path;

{I}explicit SerializationError(
{II}std::wstring a_cause
{I}) : cause(std::move(a_cause)) {{
{II}// Intentionally empty.
{I}}}
}};  // struct SerializationError"""
            ),
            *_generate_serialization_exception_implementation(),
            _generate_serialize_bool(),
            _generate_serialize_int(),
            _generate_serialize_double(),
            _generate_serialize_str(),
            _generate_serialize_bytearray(),
            _generate_serialize_list_with_fallible_item_serialization(),
            _generate_serialize_list_with_infallible_item_serialization(),
        ]
    )

    # NOTE (mristin):
    # A serializer can fail only where a number can be reached from what it
    # serializes, since a number is the only value JSON may have to refuse.
    # We compute that once, as a fixed point over the whole type graph, and
    # thread it through.
    ids_of_fallible_types = _collect_ids_of_types_with_fallible_serialization(
        symbol_table
    )

    iclass_is_fallible = any(
        intermediate.runtime_id(cls) in ids_of_fallible_types
        for cls in symbol_table.concrete_classes
    )

    if any(
        _type_annotation_contains_list_of_instances(prop.type_annotation)
        for cls in symbol_table.concrete_classes
        for prop in cls.properties
    ):
        blocks.extend(_generate_serialize_list_of_instances_overloads())

    if iclass_is_fallible:
        blocks.extend(_generate_no_json_and_error_factories())
        blocks.append(_generate_serialize_into())

    has_tuple = len(list(intermediate.tuple_arities(symbol_table))) > 0

    if iclass_is_fallible or has_tuple:
        blocks.append(_generate_as_fallible())
        blocks.append(_generate_as_fallible_identity())

    if has_tuple:
        blocks.append(_generate_deref())
        blocks.append(_generate_deref_identity())

    if intermediate.uses_json_types(symbol_table):
        blocks.extend(
            [
                _generate_serialize_json_value(),
                _generate_serialize_json_array(),
                _generate_serialize_json_object(),
            ]
        )

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_serialize_tuple_function(arity))

    if len(symbol_table.enumerations) > 0:
        blocks.append(_generate_serialize_enumeration())

    blocks.append(_generate_serialize_iclass_definition(fallible=iclass_is_fallible))

    for cls in symbol_table.concrete_classes:
        blocks.append(
            _generate_serialize_cls_declaration(
                cls=cls,
                ids_of_fallible_types=ids_of_fallible_types,
            )
        )

    for cls in symbol_table.classes:
        if _serialization_dispatches(cls):
            blocks.append(
                _generate_dispatching_serialize_cls_declaration(
                    cls=cls,
                    ids_of_fallible_types=ids_of_fallible_types,
                )
            )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_serialize_named_union_declaration(
                named_union=named_union,
                ids_of_fallible_types=ids_of_fallible_types,
            )
        )

    for cls in symbol_table.concrete_classes:
        blocks.append(
            _generate_serialize_cls(
                cls=cls,
                ids_of_fallible_types=ids_of_fallible_types,
            )
        )

    for cls in symbol_table.classes:
        if _serialization_dispatches(cls):
            blocks.append(
                _generate_dispatching_serialize_cls(
                    cls=cls,
                    ids_of_fallible_types=ids_of_fallible_types,
                )
            )

    blocks.append(
        _generate_serialize_iclass_implementation(
            symbol_table=symbol_table,
            ids_of_fallible_types=ids_of_fallible_types,
        )
    )

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_serialize_named_union_implementation(
                named_union=named_union,
                ids_of_fallible_types=ids_of_fallible_types,
            )
        )

    blocks.append(_generate_serialize_implementation(fallible=iclass_is_fallible))

    blocks.extend(
        [
            Stripped("// endregion Serialization"),
            cpp_common.generate_namespace_closing(namespace),
            cpp_common.WARNING,
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
