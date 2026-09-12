"""Generate code for JSON de/serialization."""

import io
import itertools
from typing import List, Tuple, Optional, Iterable, Final, Mapping, Union, Literal

from icontract import ensure, require

from aas_core_codegen import intermediate, specific_implementations, naming
from aas_core_codegen.common import (
    Stripped,
    indent_but_first_line,
    Identifier,
    Error,
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

{I}return std::make_pair<
{II}common::optional<double>,
{II}common::optional<DeserializationError>
{I}>(
{II}json.get<double>(),
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
{IIII}std::wstring(
{IIIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIIII}L"an array or an object), but got a value of a different, "
{IIIII}L"non-JSON-able type (possibly null)"
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
{IIII}std::wstring(
{IIIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIIII}L"an array or an object), but got a value of a different, "
{IIIII}L"non-JSON-able type (possibly null)"
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
{IIII}// NOTE (mristin):
{IIII}// ``iteration::PropertySegment`` requires an enumeration literal for
{IIII}// one of the meta-model's own properties, so it can not represent
{IIII}// an arbitrary JSON object key -- we fold the key into the message
{IIII}// instead of a structured path segment.
{IIII}error->cause = common::Concat(
{IIIII}L"At the JSON object key \\"",
{IIIII}common::Utf8ToWstring(item.key()),
{IIIII}L"\\": ",
{IIIII}error->cause
{IIII});

{IIII}return std::make_pair(common::nullopt, std::move(error));
{III}}}

{III}result[item.key()] = std::move(*serialized_value);
{II}}}

{II}return std::make_pair(std::move(result), common::nullopt);
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
{IIII}std::wstring(
{IIIII}L"Expected a JSON array, but got a value of a different JSON type"
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
{IIII}std::wstring(
{IIIII}L"Expected a JSON object, but got a value of a different JSON type"
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
{I}common::optional<std::wstring> text;
{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}text,
{II}error
{I}) = DeserializeWstring(
{II}json
{I});

{I}if (error.has_value()) {{
{II}return std::make_pair<
{III}common::optional<types::{enum_name}>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}std::move(error)
{II});
{I}}}

{I}common::optional<
{II}types::{enum_name}
{I}> literal = std::move(
{II}wstringification::{from_wstring}(
{III}*text
{II})
{I});

{I}if (!literal.has_value()) {{
{II}std::wstring message = common::Concat(
{III}L"Invalid literal for {enum_name}: ",
{III}*text
{II});

{II}return std::make_pair<
{III}common::optional<types::{enum_name}>,
{III}common::optional<DeserializationError>
{II}>(
{III}common::nullopt,
{III}common::make_optional<DeserializationError>(
{IIII}message
{III})
{II});
{I}}}

{I}return std::make_pair<
{II}common::optional<types::{enum_name}>,
{II}common::optional<DeserializationError>
{II}>(
{III}std::move(literal),
{III}common::nullopt
{II});
}}"""
    )


def _generate_concretely_deserialize_definition(
    cls: intermediate.ClassUnion,
) -> Stripped:
    """Generate the definition of the concrete ``Deserialize*`` functions."""
    interface_name = cpp_naming.interface_name(cls.name)

    if len(cls.concrete_descendants) == 0:
        function_name = cpp_naming.function_name(Identifier(f"deserialize_{cls.name}"))
    else:
        function_name = cpp_naming.function_name(
            Identifier(f"concretely_deserialize_{cls.name}")
        )

    if len(cls.ancestors) > 0:
        # NOTE (mristin):
        # We have to introduce the template so that we do not have to
        # unnecessarily upcast the instance to ancestor classes.
        prefix = Stripped(
            f"""\
template <
{I}typename T,
{I}typename std::enable_if<
{II}std::is_base_of<T, types::{interface_name}>::value
{I}>::type* = nullptr
>
std::pair<
{I}common::optional<std::shared_ptr<T> >,
{I}common::optional<DeserializationError>
>"""
        )
    else:
        prefix = Stripped(
            f"""\
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
>"""
        )

    return Stripped(
        f"""\
/**
 * \\brief Deserialize concretely an instance
 * of types::{interface_name}.
 *
 * \\param json value to be de-serialized
 * \\param additional_properties if not set, check that \\p json contains
 * no additional properties
 * \\return the deserialized instance, or an error, if any
 */
{prefix} {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
);"""
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


def _generate_deserialize_primitive_property(
    prop: intermediate.Property, ok_type: Stripped
) -> Stripped:
    """
    Generate the snippet to de-serialize the primitive property.

    We assume that the check whether the property is set is performed elsewhere.

    The ``ok_type`` denotes the type of the deserialized instance, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    primitive_type = intermediate.try_primitive_type(type_anno)

    assert (
        primitive_type is not None
    ), f"Primitive property expected, got for {prop.name!r}: {prop.type_annotation}"

    deserialize_primitive = _PRIMITIVE_TYPE_TO_DESERIALIZE[primitive_type]

    json_prop_name = prop.json_name

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialize_primitive}(
{I}json[{cpp_common.string_literal(json_prop_name)}]
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}{cpp_common.wstring_literal(json_prop_name)}
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
    )


def _generate_deserialize_json_property(
    prop: intermediate.Property,
    type_anno: intermediate.TypeAnnotationUnion,
    ok_type: Stripped,
) -> Stripped:
    """
    Generate the snippet to de-serialize the JSON-able property.

    We assume that the check whether the property is set is performed elsewhere.

    The ``ok_type`` denotes the type of the deserialized instance, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.
    """
    deserialize_function = _json_deserialize_function_for(type_anno)

    json_prop_name = prop.json_name

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialize_function}(
{I}json[{cpp_common.string_literal(json_prop_name)}]
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}{cpp_common.wstring_literal(json_prop_name)}
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
    )


def _generate_deserialize_enumeration_property(
    prop: intermediate.Property, ok_type: Stripped
) -> Stripped:
    """
    Generate the snippet to de-serialize the enumeration property.

    We assume that the check whether the property is set is performed elsewhere.

    The ``ok_type`` denotes the type of the deserialized instance, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    )

    enum = type_anno.our_type

    deserialization_function = cpp_naming.function_name(
        Identifier(f"deserialize_{enum.name}")
    )

    json_prop_name = prop.json_name

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialization_function}(
{I}json[{cpp_common.string_literal(json_prop_name)}]
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}{cpp_common.wstring_literal(json_prop_name)}
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
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


def _generate_deserialize_instance_property(
    prop: intermediate.Property, ok_type: Stripped
) -> Stripped:
    """
    Generate the snippet to de-serialize the instance property.

    We assume that the check whether the property is set is performed elsewhere.

    The ``ok_type`` denotes the type of the deserialized instance, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    deserialize_function: Stripped

    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ):
        deserialize_function = _determine_deserialize_function_for_class(
            cls=type_anno.our_type
        )

    elif isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.NamedUnion
    ):
        # NOTE (mristin):
        # A named union is not part of the class hierarchy, so there is no
        # ancestor to upcast to -- the dispatching function is always called
        # bare, without any template parameter.
        deserialize_function = Stripped(
            cpp_naming.function_name(
                Identifier(f"Deserialize_{type_anno.our_type.name}")
            )
        )

    else:
        raise AssertionError(
            f"NOTE (mristin): We expect only classes or named unions "
            f"as the instance property type, but you specified {prop.type_annotation} "
            f"in property {prop.name!r}. "
            f"Please contact the developers if you need this feature."
        )

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
    json_prop_name = prop.json_name

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = {deserialize_function}(
{I}json[{cpp_common.string_literal(json_prop_name)}],
{I}additional_properties
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}{cpp_common.wstring_literal(json_prop_name)}
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
    )


def _generate_deserialize_list_property(
    prop: intermediate.Property, ok_type: Stripped
) -> Stripped:
    """
    Generate the snippet to de-serialize the list property.

    We assume that the check whether the property is set is performed elsewhere.

    The ``ok_type`` denotes the type of the deserialized instance, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.ListTypeAnnotation)

    deserialize_item_expr: Stripped

    items_primitive_type = intermediate.try_primitive_type(type_anno.items)

    if items_primitive_type is not None:
        deserialize_item_expr = _PRIMITIVE_TYPE_TO_DESERIALIZE[items_primitive_type]

    else:
        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("This case should have been handled before.")

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                deserialize_item_expr = cpp_naming.function_name(
                    Identifier(f"deserialize_{type_anno.items.our_type.name}")
                )

            elif isinstance(
                type_anno.items.our_type, intermediate.ConstrainedPrimitive
            ):
                raise AssertionError("This case should have been handled before.")

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                deserialize_cls = _determine_deserialize_function_for_class(
                    cls=type_anno.items.our_type
                )

                deserialize_item_expr = Stripped(
                    f"""\
[&additional_properties](const nlohmann::json& a_json) {{
{I}return {deserialize_cls}(a_json, additional_properties);
}}"""
                )

            elif isinstance(type_anno.items.our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # A named union is not part of the class hierarchy, so there is no
                # ancestor to upcast to -- the dispatching function is always
                # called bare, without any template parameter.
                deserialize_cls = cpp_naming.function_name(
                    Identifier(f"Deserialize_{type_anno.items.our_type.name}")
                )

                deserialize_item_expr = Stripped(
                    f"""\
[&additional_properties](const nlohmann::json& a_json) {{
{I}return {deserialize_cls}(a_json, additional_properties);
}}"""
                )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.items.our_type)

        else:
            raise NotImplementedError(
                f"NOTE (mristin): We currently generate only JSON de-serialization "
                f"code for lists of atomic values, "
                f"but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
    json_prop_name = prop.json_name

    items_type = cpp_common.generate_type(
        type_anno.items, types_namespace=cpp_common.TYPES_NAMESPACE
    )

    return Stripped(
        f"""\
std::tie(
{I}{var_name},
{I}error
) = DeserializeList<{items_type}>(
{I}json[{cpp_common.string_literal(json_prop_name)}],
{I}{indent_but_first_line(deserialize_item_expr, I)}
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}{cpp_common.wstring_literal(json_prop_name)}
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
    )


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


def _generate_deserialize_tuple_property(
    prop: intermediate.Property, ok_type: Stripped
) -> Stripped:
    """
    Generate the snippet to de-serialize the tuple property.

    We assume that the check whether the property is set is performed elsewhere.

    The ``ok_type`` denotes the type of the deserialized instance, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.

    The actual array/length checks, per-item de-serialization and error-path
    bookkeeping are delegated to the generic ``DeserializeTupleN`` function
    generated once for the tuple's arity by
    :py:func:`_generate_deserialize_tuple_function`.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    assert isinstance(type_anno, intermediate.TupleTypeAnnotation)

    var_name = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))
    json_prop_name = prop.json_name
    json_prop_name_literal = cpp_common.string_literal(json_prop_name)

    item_types = []  # type: List[Stripped]
    item_exprs = []  # type: List[Stripped]

    for item_type_anno in type_anno.items:
        assert isinstance(item_type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
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
std::tie(
{I}{var_name},
{I}error
) = {function_name}<
{I}{indent_but_first_line(item_types_joined, I)}
>(
{I}json[{json_prop_name_literal}],
{I}{indent_but_first_line(item_exprs_joined, I)}
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}{cpp_common.wstring_literal(json_prop_name)}
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
    )


def _generate_deserialize_property(
    prop: intermediate.Property, ok_type: Stripped
) -> Stripped:
    """
    Generate the snippet to de-serialize the given property.

    The ``ok_type`` denotes the type of the deserialized value, *not* the property.
    We have to distinguish between cases where we directly create an upcast pointer to
    an ancestor class, and cases where there are no ancestor classes.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    code: Stripped

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        code = _generate_deserialize_primitive_property(prop=prop, ok_type=ok_type)

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            code = _generate_deserialize_enumeration_property(
                prop=prop, ok_type=ok_type
            )

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            code = _generate_deserialize_primitive_property(prop=prop, ok_type=ok_type)

        elif isinstance(
            type_anno.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ):
            code = _generate_deserialize_instance_property(prop=prop, ok_type=ok_type)

        elif isinstance(type_anno.our_type, intermediate.NamedUnion):
            code = _generate_deserialize_instance_property(prop=prop, ok_type=ok_type)

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        code = _generate_deserialize_list_property(prop=prop, ok_type=ok_type)
    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        code = _generate_deserialize_tuple_property(prop=prop, ok_type=ok_type)
    elif isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        code = _generate_deserialize_json_property(
            prop=prop, type_anno=type_anno, ok_type=ok_type
        )
    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        json_prop_literal = cpp_common.string_literal(prop.json_name)

        code = Stripped(
            f"""\
if (json.contains({json_prop_literal})) {{
{I}{indent_but_first_line(code, I)}
}}"""
        )

    return code


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_concretely_deserialize_implementation(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the concrete deserialization for the class ``cls``.

    It is assumed that the dispatch has been already effectuated to this generated
    function, so no further dispatch should be performed.
    """
    if cls.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"jsonization/deserialize_{cls.name}.cpp"
        )

        code = spec_impls.get(implementation_key, None)
        if code is None:
            return None, Error(
                cls.parsed.node,
                f"The implementation is missing for the JSON deserialization "
                f"of {cls.name!r}: {implementation_key}",
            )
        return code, None

    interface_name = cpp_naming.interface_name(cls.name)

    if len(cls.ancestors) == 0:
        # NOTE (mristin):
        # We will not need to upcast this instance, so the return value type
        # is simply the interface.
        ok_type = Stripped(f"types::{interface_name}")
    else:
        # NOTE (mristin):
        # We have to leave it open to upcast to an ancestor class, and hence
        # we introduce a template parameter.
        ok_type = Stripped("T")

    expected_properties = cpp_naming.constant_name(
        Identifier(f"properties_in_{cls.name}")
    )

    blocks = [
        Stripped(
            f"""\
if (!json.is_object()) {{
{I}std::wstring message = common::Concat(
{II}L"Expected an object, but got: ",
{II}common::Utf8ToWstring(json.type_name())
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}message
{II})
{I});
}}"""
        ),
        Stripped(
            f"""\
if (!additional_properties) {{
{I}for (const auto& key_val : json.items()) {{
{II}auto it(
{III}{expected_properties}.find(key_val.key())
{II});
{II}if (it == {expected_properties}.end()) {{
{III}std::wstring message = common::Concat(
{IIII}L"Unexpected additional property: ",
{IIII}common::Utf8ToWstring(key_val.key())
{III});

{III}return std::make_pair<
{IIII}common::optional<std::shared_ptr<{ok_type}> >,
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
        ),
    ]  # type: List[Stripped]

    class_name = cpp_naming.class_name(cls.name)

    if len(cls.properties) == 0:
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
{II}new types::{class_name}()
{I}),
{I}common::nullopt
);"""
            )
        )
    else:
        json_names_of_required_properties = [
            prop.json_name
            for prop in cls.properties
            if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
        ]  # type: List[str]

        if cls.serialization.with_model_type:
            json_names_of_required_properties.append(
                naming.json_property(Identifier("model_type"))
            )

        if len(json_names_of_required_properties) > 0:
            blocks.append(Stripped("// region Check required properties"))
            for json_prop_name in json_names_of_required_properties:
                json_prop_name_literal = cpp_common.string_literal(json_prop_name)
                blocks.append(
                    Stripped(
                        f"""\
if (!json.contains({json_prop_name_literal})) {{
{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}L"The required property {json_prop_name} is missing"
{II})
{I});
}}"""
                    )
                )

            blocks.append(Stripped("// endregion Check required properties"))

        # region Initialization
        blocks.append(Stripped("// region Initialization"))

        if len(cls.properties) > 0:
            blocks.append(Stripped("common::optional<DeserializationError> error;"))

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
                else:
                    if var_type.endswith(">"):
                        var_type = Stripped(f"common::optional<{var_type} >")
                    else:
                        var_type = Stripped(f"common::optional<{var_type}>")

            init_statements.append(Stripped(f"{var_type} {var_name};"))

        blocks.append(Stripped("\n\n".join(init_statements)))

        blocks.append(Stripped("// endregion Initialization"))
        # endregion

        # region Deserialize properties
        for prop in cls.properties:
            json_prop_name = prop.json_name
            blocks.append(Stripped(f"// region De-serialize {json_prop_name}"))

            blocks.append(_generate_deserialize_property(prop=prop, ok_type=ok_type))

            blocks.append(Stripped(f"// endregion De-serialize {json_prop_name}"))
        # endregion

        if cls.serialization.with_model_type:
            # NOTE (mristin):
            # If the serialization requires a model type, we consequently check for it
            # here. The model type thus obtained is *not* used for any dispatch. We only
            # use this value for verification to make sure that the model type
            # of the instances is consistent with the expected value for its concrete
            # class. This will be performed even though the code might have had to parse
            # model type before for the dispatch. We decided to double-check to cover
            # the case where a dispatch is *unnecessary* (*e.g.*, the caller knows the
            # expected runtime type), but the model type might still be invalid in the
            # input. Hence, when the dispatch is *necessary*, the model type JSON
            # property will be parsed twice, which is a cost we currently find
            # acceptable.

            blocks.append(
                Stripped(
                    """\
// region Check model type
// This check is intended only for verification, not for dispatch."""
                )
            )

            model_type = naming.json_model_type(cls.name)

            blocks.append(
                Stripped(
                    f"""\
common::optional<
{I}std::wstring
> model_type;

std::tie(
{I}model_type,
{I}error
) = DeserializeWstring(
{I}json["modelType"]
);

if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<PropertySegment>(
{III}L"modelType"
{II})
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}

if (*model_type != L"{model_type}") {{
{I}std::wstring message = common::Concat(
{II}L"Expected model type '{model_type}', "
{II}L"but got: ",
{II}*model_type
{I});

{I}error = common::make_optional<DeserializationError>(
{II}message
{I});

{I}return std::make_pair<
{II}common::optional<std::shared_ptr<{ok_type}> >,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}std::move(error)
{I});
}}"""
                )
            )

            blocks.append(Stripped("// endregion Check model type"))

        # region Pass arguments to the constructor
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
{II}new types::{class_name}(
{III}{indent_but_first_line(constructor_args_joined, III)}
{II})
{I}),
{I}common::nullopt
);"""
            )
        )
        # endregion

    body = "\n\n".join(blocks)

    if len(cls.concrete_descendants) == 0:
        function_name = cpp_naming.function_name(Identifier(f"deserialize_{cls.name}"))
    else:
        function_name = cpp_naming.function_name(
            Identifier(f"concretely_deserialize_{cls.name}")
        )

    if len(cls.ancestors) > 0:
        # NOTE (mristin):
        # We have to introduce the template so that we do not have to
        # unnecessarily upcast the instance to ancestor classes.
        prefix = Stripped(
            f"""\
template <
{I}typename T,
{I}typename std::enable_if<
{II}std::is_base_of<T, types::{interface_name}>::value
{I}>::type*
>
std::pair<
{I}common::optional<std::shared_ptr<T> >,
{I}common::optional<DeserializationError>
>"""
        )
    else:
        prefix = Stripped(
            f"""\
std::pair<
{I}common::optional<
{II}std::shared_ptr<types::{interface_name}>
{I}>,
{I}common::optional<DeserializationError>
>"""
        )

    expected_properties_literals = [
        f"{cpp_common.string_literal(prop.json_name)}" for prop in cls.properties
    ]

    if cls.serialization.with_model_type:
        expected_properties_literals.append(cpp_common.string_literal("modelType"))

    expected_properties_literals_joined = ",\n".join(expected_properties_literals)

    expected_properties_definition = Stripped(
        f"""\
std::set<std::string> {expected_properties} = {{
{I}{indent_but_first_line(expected_properties_literals_joined, I)}
}};"""
    )

    return (
        Stripped(
            f"""\
{expected_properties_definition}

{prefix} {function_name}(
{I}const nlohmann::json& json,
{I}bool additional_properties
) {{
{I}{indent_but_first_line(body, I)}
}}"""
        ),
        None,
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

        if len(target_cls.concrete_descendants) > 0:
            target_function = cpp_naming.function_name(
                Identifier(f"concretely_deserialize_{target_cls.name}")
            )
        else:
            target_function = cpp_naming.function_name(
                Identifier(f"deserialize_{target_cls.name}")
            )

        if len(target_cls.ancestors) > 0:
            # NOTE (mristin):
            # ``target_function`` is only templated if ``target_cls`` itself
            # has ancestors (see ``_generate_concretely_deserialize_definition``)
            # -- true for every proper descendant (which always has ``cls``
            # among its ancestors), but *not* necessarily true when
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
{II}return std::make_pair<
{III}common::optional<std::shared_ptr<types::{interface_name}> >,
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
{III}common::optional<std::shared_ptr<types::{interface_name}> >,
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
{IIII}L"types::{interface_name} "
{IIII}L"is not defined for model type: ",
{IIII}common::Utf8ToWstring(*model_type_str)
{III});

{III}return std::make_pair<
{IIII}common::optional<std::shared_ptr<types::{interface_name}> >,
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
        ),
    ]


def _generate_wrap_deserialized_as_variant_function() -> Stripped:
    """
    Generate the generic helper to wrap a de-serialized pointer as a variant.

    Every implementer of a named union is de-serialized through its own
    canonical entry point (bypassing the union), and the resulting pointer
    then needs to be wrapped into the union's ``std::variant`` alternative
    matching its own interface -- no upcasting is involved, since the
    variant is spelled out over the implementers' own interfaces directly.
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
 * then needs to be wrapped into the union's std::variant alternative
 * matching its own interface -- no upcasting is involved, since the
 * variant is spelled out over the implementers' own interfaces directly.
 *
 * \\param result the result of a de-serialization call for one implementer
 * \\return the result wrapped as a variant, or the propagated error
 */
template <typename VariantT, typename T>
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
{III}VariantT(std::move(*result.first)),
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
    target_cls: intermediate.ConcreteClass, union_name: Identifier
) -> Stripped:
    """
    Generate the snippet to de-serialize a single implementer and wrap it.

    The implementer is de-serialized through its own canonical entry point
    (bypassing the union), and the resulting
    ``pair<optional<shared_ptr<T>>, ...>`` is wrapped into the union's
    ``std::variant`` in one call via
    :py:func:`_generate_wrap_deserialized_as_variant_function`.
    """
    if len(target_cls.concrete_descendants) > 0:
        target_function = cpp_naming.function_name(
            Identifier(f"concretely_deserialize_{target_cls.name}")
        )
    else:
        target_function = cpp_naming.function_name(
            Identifier(f"deserialize_{target_cls.name}")
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
return WrapDeserializedAsVariant<types::{union_name}>(
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
if (!json.is_object()) {{
{I}std::wstring message = common::Concat(
{II}L"Expected an object, but got: ",
{II}common::Utf8ToWstring(json.type_name())
{I});

{I}return std::make_pair<
{II}common::optional<types::{union_name}>,
{II}common::optional<DeserializationError>
{I}>(
{II}common::nullopt,
{II}common::make_optional<DeserializationError>(
{III}message
{II})
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
                    target_cls=target_cls, union_name=union_name
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
            target_cls=target_cls, union_name=union_name
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
{I}common::optional<
{II}{indent_but_first_line(value_type, II)}
{I}> instance;

{I}common::optional<DeserializationError> error;

{I}std::tie(
{II}instance,
{II}error
{I}) = {indent_but_first_line(deserialize_function, I)}(
{II}json,
{II}additional_properties
{I});

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
    """
    Generate the function to serialize a double to a JSON value.

    Named to match ``DeserializeDouble``, even though converting a C++
    ``double`` to a JSON value can not actually fail.
    """
    return Stripped(
        f"""\
/**
 * Serialize the given floating-point number to a JSON value.
 */
nlohmann::json SerializeDouble(
{I}double value
) {{
{I}return value;
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
{II}std::move(
{III}stringification::Base64Encode(bytes)
{II})
{I});
}}"""
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
    callable, which must return a
    ``std::pair<common::optional<nlohmann::json>, common::optional<SerializationError>>``
    regardless of whether the item's own JSON conversion can actually fail --
    mirroring how ``SerializeListWithFallible`` expects a fallible callable for
    every list item.
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
) = serialize_item{i}(
{I}std::get<{i}>(value)
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


def _generate_identity() -> Stripped:
    """Generate the function for identity serialization which we can pass to list serialization."""
    return Stripped(
        f"""\
/**
 * Just forward the value as it is.
 */
template<typename T>
const T& Identity(const T& value) {{
{I}return value;
}}"""
    )


def _generate_serialize_iclass_definition() -> List[Stripped]:
    """Generate the definition of the main dispatch for serializing ``IClass``."""
    return [
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeIClass(
{I}const types::IClass& that
);"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeIClassPtr(
{I}const std::shared_ptr<types::IClass>& that
);"""
        ),
    ]


def _generate_serialize_primitive_property(
    getter_expr: Stripped,
    primitive_type: intermediate.PrimitiveType,
    property_name: Identifier,
    json_name: str,
) -> Stripped:
    """
    Generate the snippet to serialize the given primitive property.

    The ``getter_expr`` refers to the C++ expression specifying the value
    to be serialized.

    The ``property_name`` refers to the intermediate property name, and
    the ``json_name`` to its name in the JSON serialization.
    """
    json_prop_name_literal = cpp_common.string_literal(json_name)

    if primitive_type is intermediate.PrimitiveType.BOOL:
        return Stripped(
            f"""\
result[{json_prop_name_literal}] = SerializeBool(
{I}{getter_expr}
);"""
        )

    elif primitive_type is intermediate.PrimitiveType.INT:
        serialized_var = cpp_naming.variable_name(Identifier(f"json_{property_name}"))
        return Stripped(
            f"""\
common::optional<nlohmann::json> {serialized_var};
std::tie(
{I}{serialized_var},
{I}error
) = SerializeInt64(
{I}{indent_but_first_line(getter_expr, I)}
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::PropertySegment>(
{III}iteration::Property::{cpp_naming.enum_literal_name(property_name)}
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

result[{json_prop_name_literal}] = std::move(
{I}{serialized_var}.value()
);"""
        )
    elif primitive_type is intermediate.PrimitiveType.FLOAT:
        return Stripped(
            f"""\
result[{json_prop_name_literal}] = SerializeDouble(
{I}{getter_expr}
);"""
        )

    elif primitive_type is intermediate.PrimitiveType.STR:
        return Stripped(
            f"""\
result[{json_prop_name_literal}] = SerializeWstring(
{I}{indent_but_first_line(getter_expr, II)}
);"""
        )

    elif primitive_type is intermediate.PrimitiveType.BYTEARRAY:
        return Stripped(
            f"""\
result[{json_prop_name_literal}] = stringification::Base64Encode(
{I}{getter_expr}
);"""
        )
    else:
        # noinspection PyTypeChecker
        assert_never(primitive_type)


def _generate_serialize_json_property(
    getter_expr: Stripped,
    type_anno: intermediate.TypeAnnotationUnion,
    property_name: Identifier,
    json_name: str,
) -> Stripped:
    """
    Generate the snippet to serialize the given JSON-able property.

    The ``getter_expr`` refers to the C++ expression specifying the value
    to be serialized.

    The ``property_name`` refers to the intermediate property name, and
    the ``json_name`` to its name in the JSON serialization.
    """
    json_prop_name_literal = cpp_common.string_literal(json_name)
    serialize_function = _json_serialize_function_for(type_anno)
    serialized_var = cpp_naming.variable_name(Identifier(f"json_{property_name}"))

    return Stripped(
        f"""\
common::optional<nlohmann::json> {serialized_var};
std::tie(
{I}{serialized_var},
{I}error
) = {serialize_function}(
{I}{indent_but_first_line(getter_expr, I)}
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::PropertySegment>(
{III}iteration::Property::{cpp_naming.enum_literal_name(property_name)}
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

result[{json_prop_name_literal}] = std::move(
{I}{serialized_var}.value()
);"""
    )


def _generate_serialize_list_property(
    getter_expr: Stripped,
    type_anno: intermediate.ListTypeAnnotation,
    property_name: Identifier,
    json_name: str,
) -> Stripped:
    """
    Generate the snippet to serialize the given property as a list.

    The ``getter_expr`` refers to the C++ expression specifying the list
    to be serialized.

    The ``property_name`` refers to the intermediate property name, and
    the ``json_name`` to its name in the JSON serialization.
    """
    serialize_list: Union[
        Literal["SerializeListWithFallible"], Literal["SerializeListWithInfallible"]
    ]

    serialize_item_expr: Stripped

    items_primitive_type = intermediate.try_primitive_type(type_anno.items)

    if items_primitive_type is not None:
        if items_primitive_type is intermediate.PrimitiveType.BOOL:
            serialize_list = "SerializeListWithInfallible"

            serialize_item_expr = Stripped("SerializeBool")

        elif items_primitive_type is intermediate.PrimitiveType.INT:
            serialize_list = "SerializeListWithFallible"

            serialize_item_expr = Stripped("SerializeInt64")

        elif items_primitive_type is intermediate.PrimitiveType.FLOAT:
            serialize_list = "SerializeListWithInfallible"

            serialize_item_expr = Stripped("SerializeDouble")

        elif items_primitive_type is intermediate.PrimitiveType.STR:
            serialize_list = "SerializeListWithInfallible"

            serialize_item_expr = Stripped("SerializeWstring")

        elif items_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
            serialize_list = "SerializeListWithInfallible"

            serialize_item_expr = Stripped("stringification::Base64Encode")

        else:
            # noinspection PyTypeChecker
            assert_never(items_primitive_type)

    else:
        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected this case to be handled before")

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                serialize_list = "SerializeListWithInfallible"

                enum_name = cpp_naming.enum_name(type_anno.items.our_type.name)

                # NOTE (mristin):
                # We have to make a lambda since passing
                # stringification::to_string<enum name> results in ambiguous grammar
                # in C++: the ``<`` and ``>`` are interpreted as less and greater
                # operators.
                serialize_item_expr = Stripped(
                    f"""\
[](const types::{enum_name}& an_item) {{
{I}return stringification::to_string(an_item);
}}"""
                )

            elif isinstance(
                type_anno.items.our_type, intermediate.ConstrainedPrimitive
            ):
                raise AssertionError("Expected this case to be handled before")

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                serialize_list = "SerializeListWithFallible"

                serialize_item_expr = Stripped("SerializeIClassPtr")

            elif isinstance(type_anno.items.our_type, intermediate.NamedUnion):
                serialize_list = "SerializeListWithFallible"

                union_name = cpp_naming.union_name(type_anno.items.our_type.name)
                serialize_item_expr = Stripped(f"Serialize{union_name}")

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.items.our_type)

        else:
            raise NotImplementedError(
                f"(mristin) We currently generate JSON serialization code only for "
                f"lists of atomic values, but we got: {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

    json_prop_name_literal = cpp_common.string_literal(json_name)

    if serialize_list == "SerializeListWithInfallible":
        return Stripped(
            f"""\
result[{json_prop_name_literal}] = {serialize_list}(
{I}{indent_but_first_line(getter_expr, I)},
{I}{indent_but_first_line(serialize_item_expr, I)}
);"""
        )

    elif serialize_list == "SerializeListWithFallible":
        serialized_var = cpp_naming.variable_name(Identifier(f"json_{property_name}"))

        return Stripped(
            f"""\
common::optional<nlohmann::json> {serialized_var};
std::tie(
{I}{serialized_var},
{I}error
) = {serialize_list}(
{I}{indent_but_first_line(getter_expr, I)},
{I}{serialize_item_expr}
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::PropertySegment>(
{III}iteration::Property::{cpp_naming.enum_literal_name(property_name)}
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

result[{json_prop_name_literal}] = std::move(
{I}{serialized_var}.value()
);"""
        )

    else:
        # noinspection PyTypeChecker
        assert_never(serialize_list)


def _generate_serialize_tuple_property(
    getter_expr: Stripped,
    type_anno: intermediate.TupleTypeAnnotation,
    property_name: Identifier,
    json_name: str,
) -> Stripped:
    """
    Generate the snippet to serialize the given property as a tuple.

    The ``getter_expr`` refers to the C++ expression specifying the tuple
    to be serialized.

    The ``property_name`` refers to the intermediate property name, and
    the ``json_name`` to its name in the JSON serialization.

    Every per-item closure built here is normalized to return
    ``std::pair<common::optional<nlohmann::json>, common::optional<SerializationError>>``
    -- even for primitive kinds whose own JSON conversion can never fail --
    so that the generic ``SerializeTupleN`` (see
    :py:func:`_generate_serialize_tuple_function`) can treat every item
    uniformly. The actual per-item error-path bookkeeping is delegated to
    that generic function.
    """
    item_exprs = []  # type: List[Stripped]

    for item_type_anno in type_anno.items:
        assert isinstance(item_type_anno, intermediate.AtomicTypeAnnotationAsTuple), (
            "Tuple items are restricted to atomic types (primitives, "
            "constrained primitives, classes and enumerations) by "
            "intermediate._translate._verify_only_simple_type_patterns, so no "
            "nested optionals, lists or tuples are expected here."
        )

        items_primitive_type = intermediate.try_primitive_type(item_type_anno)

        if items_primitive_type is not None:
            if items_primitive_type is intermediate.PrimitiveType.BOOL:
                item_exprs.append(
                    Stripped(
                        f"""\
[](bool item) {{
{I}return std::make_pair(
{II}common::make_optional<nlohmann::json>(item),
{II}common::nullopt
{I});
}}"""
                    )
                )

            elif items_primitive_type is intermediate.PrimitiveType.INT:
                item_exprs.append(Stripped("SerializeInt64"))

            elif items_primitive_type is intermediate.PrimitiveType.FLOAT:
                item_exprs.append(
                    Stripped(
                        f"""\
[](double item) {{
{I}return std::make_pair(
{II}common::make_optional<nlohmann::json>(item),
{II}common::nullopt
{I});
}}"""
                    )
                )

            elif items_primitive_type is intermediate.PrimitiveType.STR:
                item_exprs.append(
                    Stripped(
                        f"""\
[](const std::wstring& item) {{
{I}return std::make_pair(
{II}common::make_optional<nlohmann::json>(
{III}SerializeWstring(item)
{II}),
{II}common::nullopt
{I});
}}"""
                    )
                )

            elif items_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                item_exprs.append(
                    Stripped(
                        f"""\
[](const std::vector<std::uint8_t>& item) {{
{I}return std::make_pair(
{II}common::make_optional<nlohmann::json>(
{III}stringification::Base64Encode(item)
{II}),
{II}common::nullopt
{I});
}}"""
                    )
                )

            else:
                # noinspection PyTypeChecker
                assert_never(items_primitive_type)

        elif isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected this case to be handled before")

        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
            if isinstance(item_type_anno.our_type, intermediate.Enumeration):
                enum_name = cpp_naming.enum_name(item_type_anno.our_type.name)

                item_exprs.append(
                    Stripped(
                        f"""\
[](types::{enum_name} item) {{
{I}return std::make_pair(
{II}common::make_optional<nlohmann::json>(
{III}stringification::to_string(item)
{II}),
{II}common::nullopt
{I});
}}"""
                    )
                )

            elif isinstance(item_type_anno.our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected this case to be handled before")

            elif isinstance(item_type_anno.our_type, intermediate.NamedUnion):
                union_name = cpp_naming.union_name(item_type_anno.our_type.name)
                item_exprs.append(Stripped(f"Serialize{union_name}"))

            elif isinstance(
                item_type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                item_type = cpp_common.generate_type(
                    item_type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
                )

                item_exprs.append(
                    Stripped(
                        f"""\
[](
{I}const {indent_but_first_line(item_type, I)}& item
) {{
{I}return SerializeIClass(
{II}*item
{I});
}}"""
                    )
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
            item_exprs.append(_json_serialize_function_for(item_type_anno))

        else:
            # noinspection PyTypeChecker
            assert_never(item_type_anno)

    item_exprs_joined = ",\n".join(item_exprs)

    json_prop_name_literal = cpp_common.string_literal(json_name)
    serialized_var = cpp_naming.variable_name(Identifier(f"json_{property_name}"))
    function_name = f"SerializeTuple{len(type_anno.items)}"

    return Stripped(
        f"""\
common::optional<nlohmann::json> {serialized_var};
std::tie(
{I}{serialized_var},
{I}error
) = {function_name}(
{I}{indent_but_first_line(getter_expr, I)},
{I}{indent_but_first_line(item_exprs_joined, I)}
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::PropertySegment>(
{III}iteration::Property::{cpp_naming.enum_literal_name(property_name)}
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

result[{json_prop_name_literal}] = std::move(
{I}*{serialized_var}
);"""
    )


def _generate_serialize_property(prop: intermediate.Property) -> Stripped:
    """Generate code snippet to serialize the property ``prop``."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    code = None  # type: Optional[Stripped]

    getter = cpp_naming.getter_name(prop.name)
    maybe_var = None
    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        maybe_var = cpp_naming.variable_name(Identifier(f"maybe_{prop.name}"))
        getter_expr = Stripped(f"*{maybe_var}")
    else:
        getter_expr = Stripped(f"that.{getter}()")

    json_prop_name = prop.json_name

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        code = _generate_serialize_primitive_property(
            getter_expr=getter_expr,
            primitive_type=type_anno.a_type,
            property_name=prop.name,
            json_name=json_prop_name,
        )

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            code = Stripped(
                f"""\
result[{cpp_common.string_literal(json_prop_name)}] = stringification::to_string(
{I}{indent_but_first_line(getter_expr, I)}
);"""
            )
        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            code = _generate_serialize_primitive_property(
                getter_expr=getter_expr,
                primitive_type=type_anno.our_type.constrainee,
                property_name=prop.name,
                json_name=json_prop_name,
            )
        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            serialized_var = cpp_naming.variable_name(Identifier(f"json_{prop.name}"))

            code = Stripped(
                f"""\
common::optional<nlohmann::json> {serialized_var};
std::tie(
{I}{serialized_var},
{I}error
) = SerializeIClass(
{I}*{indent_but_first_line(getter_expr, I)}
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::PropertySegment>(
{III}iteration::Property::{cpp_naming.enum_literal_name(prop.name)}
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

result[{cpp_common.string_literal(json_prop_name)}] = std::move(
{I}*{serialized_var}
);"""
            )
        elif isinstance(type_anno.our_type, intermediate.NamedUnion):
            serialized_var = cpp_naming.variable_name(Identifier(f"json_{prop.name}"))

            union_name = cpp_naming.union_name(type_anno.our_type.name)

            code = Stripped(
                f"""\
common::optional<nlohmann::json> {serialized_var};
std::tie(
{I}{serialized_var},
{I}error
) = Serialize{union_name}(
{I}{indent_but_first_line(getter_expr, I)}
);
if (error.has_value()) {{
{I}error->path.segments.emplace_front(
{II}common::make_unique<iteration::PropertySegment>(
{III}iteration::Property::{cpp_naming.enum_literal_name(prop.name)}
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

result[{cpp_common.string_literal(json_prop_name)}] = std::move(
{I}*{serialized_var}
);"""
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        code = _generate_serialize_list_property(
            getter_expr=getter_expr,
            type_anno=type_anno,
            property_name=prop.name,
            json_name=json_prop_name,
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        code = _generate_serialize_tuple_property(
            getter_expr=getter_expr,
            type_anno=type_anno,
            property_name=prop.name,
            json_name=json_prop_name,
        )

    elif isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        code = _generate_serialize_json_property(
            getter_expr=getter_expr,
            type_anno=type_anno,
            property_name=prop.name,
            json_name=json_prop_name,
        )

    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)

    assert code is not None

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        maybe_var_type = cpp_common.generate_type_with_const_ref_if_applicable(
            type_annotation=prop.type_annotation,
            types_namespace=cpp_common.TYPES_NAMESPACE,
        )

        assert maybe_var is not None

        code = Stripped(
            f"""\
{maybe_var_type} {maybe_var}(
{I}that.{getter}()
);
if (that.{getter}().has_value()) {{
{I}{indent_but_first_line(code, I)}
}}"""
        )

    return code


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_serialize_cls(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the serialization function for the class ``cls``."""
    if cls.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"jsonization/serialize_{cls.name}.cpp"
        )

        code = spec_impls.get(implementation_key, None)
        if code is None:
            return None, Error(
                cls.parsed.node,
                f"The implementation is missing for the JSON serialization "
                f"of {cls.name!r}: {implementation_key}",
            )
        return code, None

    blocks = [
        Stripped(
            """\
nlohmann::json result = nlohmann::json::object();"""
        )
    ]  # type: List[Stripped]

    needs_error = False
    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)
        primitive_type = intermediate.try_primitive_type(type_anno)

        if primitive_type is not None and (
            primitive_type is intermediate.PrimitiveType.INT
        ):
            needs_error = True
            break

        if isinstance(type_anno, intermediate.OurTypeAnnotation):
            needs_error = True
            break

        if isinstance(
            type_anno,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            needs_error = True
            break

        if isinstance(type_anno, intermediate.ListTypeAnnotation):
            items_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if items_primitive_type is intermediate.PrimitiveType.INT:
                needs_error = True
                break

            if isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                needs_error = True
                break

            if isinstance(
                type_anno.items,
                (
                    intermediate.JsonValueTypeAnnotation,
                    intermediate.JsonArrayTypeAnnotation,
                    intermediate.JsonObjectTypeAnnotation,
                ),
            ):
                needs_error = True
                break

        if isinstance(type_anno, intermediate.TupleTypeAnnotation):
            for item_type_anno in type_anno.items:
                item_primitive_type = intermediate.try_primitive_type(item_type_anno)

                if item_primitive_type is intermediate.PrimitiveType.INT:
                    needs_error = True
                    break

                if isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                    needs_error = True
                    break

                if isinstance(
                    item_type_anno,
                    (
                        intermediate.JsonValueTypeAnnotation,
                        intermediate.JsonArrayTypeAnnotation,
                        intermediate.JsonObjectTypeAnnotation,
                    ),
                ):
                    needs_error = True
                    break

            if needs_error:
                break

    if needs_error:
        blocks.append(Stripped("common::optional<SerializationError> error;"))

    for prop in cls.properties:
        blocks.append(_generate_serialize_property(prop=prop))

    if cls.serialization.with_model_type:
        model_type_literal = cpp_common.string_literal(naming.json_model_type(cls.name))
        blocks.append(Stripped(f'result["modelType"] = {model_type_literal};'))

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

    blocks_joined = "\n\n".join(blocks)

    serialize_name = cpp_naming.function_name(Identifier(f"serialize_{cls.name}"))

    interface_name = cpp_naming.interface_name(cls.name)

    return (
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> {serialize_name}(
{I}const types::{interface_name}& that
) {{
{I}{indent_but_first_line(blocks_joined, I)}
}}"""
        ),
        None,
    )


def _generate_serialize_iclass_implementation(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the main dispatch function for serializing ``IClass``."""
    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        serialize_name = cpp_naming.function_name(Identifier(f"serialize_{cls.name}"))

        model_type_literal = cpp_naming.enum_literal_name(cls.name)
        model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))

        interface_name = cpp_naming.interface_name(cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case types::{model_type_enum}::{model_type_literal}:
{I}return {serialize_name}(
{II}dynamic_cast<const types::{interface_name}&>(that)
{I});"""
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

    return [
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeIClass(
{I}const types::IClass& that
) {{
{I}switch (that.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
        ),
        Stripped(
            f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> SerializeIClassPtr(
{I}const std::shared_ptr<types::IClass>& that
) {{
{I}return SerializeIClass(*that);
}}"""
        ),
    ]


def _generate_serialize_named_union_declaration(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the forward declaration of a named union's ``Serialize`` function.

    We emit this once per union, before any class's own serialize
    implementation that might reference it by name (this mirrors
    :py:func:`_generate_serialize_iclass_definition`) -- otherwise a class
    with a union-typed property would call a not-yet-declared function.
    """
    union_name = cpp_naming.union_name(named_union.name)

    return Stripped(
        f"""\
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> Serialize{union_name}(
{I}const types::{union_name}& that
);"""
    )


@require(lambda named_union: len(named_union.implementers) > 0)
def _generate_serialize_named_union_implementation(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the function to serialize a named union, once per union.

    This mirrors :py:func:`_generate_serialize_iclass_implementation`'s
    ``switch``-based dispatch shape, but switches on the ``std::variant``'s
    own ``index()`` instead of ``model_type()`` -- the variant already knows
    which alternative it holds, so no dynamic cast is needed either. We
    generate this once per named union and reference it *by name* wherever
    the union appears (property, list item, tuple item), instead of
    inlining a lambda at every use site.
    """
    union_name = cpp_naming.union_name(named_union.name)

    case_blocks = []  # type: List[Stripped]
    for i, implementer in enumerate(named_union.implementers):
        # NOTE (mristin):
        # We call the implementer's own serialize function directly on the
        # dereferenced pointer, instead of going through ``SerializeIClassPtr``
        # -- the variant's index already tells us the concrete type
        # unambiguously, so a second (redundant) dispatch by ``model_type()``
        # with a ``dynamic_cast`` would be pure waste.
        serialize_function = cpp_naming.function_name(
            Identifier(f"serialize_{implementer.name}")
        )

        case_blocks.append(
            Stripped(
                f"""\
case {i}:
{I}return {serialize_function}(*std::get<{i}>(that));"""
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
std::pair<
{I}common::optional<nlohmann::json>,
{I}common::optional<SerializationError>
> Serialize{union_name}(
{I}const types::{union_name}& that
) {{
{I}switch (that.index()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}};
}}"""
    )


def _generate_serialize_implementation() -> Stripped:
    """Generate the main serialization function."""
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
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
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
    ]

    if intermediate.model_uses_json_types(symbol_table):
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

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_deserialize_tuple_function(arity))

    for enumeration in symbol_table.enumerations:
        blocks.append(_generate_deserialize_enumeration(enumeration))

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            blocks.append(
                _generate_concretely_deserialize_definition(
                    cls=cls,
                )
            )

        if len(cls.concrete_descendants) > 0:
            blocks.append(_generate_dispatch_deserialize_definition(cls=cls))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_dispatch_deserialize_definition_for_named_union(
                named_union=named_union
            )
        )

    errors = []  # type: List[Error]

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.ConcreteClass):
            deserialize_block, error = _generate_concretely_deserialize_implementation(
                cls=cls,
                spec_impls=spec_impls,
            )
            if error is not None:
                errors.append(error)
                continue

            assert deserialize_block is not None
            blocks.append(deserialize_block)

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

    if intermediate.model_uses_json_types(symbol_table):
        blocks.extend(
            [
                _generate_serialize_json_value(),
                _generate_serialize_json_array(),
                _generate_serialize_json_object(),
            ]
        )

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_serialize_tuple_function(arity))

    blocks.extend(_generate_serialize_iclass_definition())

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_serialize_named_union_declaration(named_union=named_union)
        )

    for cls in symbol_table.concrete_classes:
        serialize_block, error = _generate_serialize_cls(cls=cls, spec_impls=spec_impls)
        if error is not None:
            errors.append(error)
        else:
            assert serialize_block is not None
            blocks.append(serialize_block)

    blocks.extend(_generate_serialize_iclass_implementation(symbol_table=symbol_table))

    for named_union in symbol_table.named_unions:
        blocks.append(
            _generate_serialize_named_union_implementation(named_union=named_union)
        )

    blocks.append(_generate_serialize_implementation())

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

    return writer.getvalue(), None


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
