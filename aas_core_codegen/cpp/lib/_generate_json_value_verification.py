"""Generate code for the exhaustive verification of JSON-able values."""

# NOTE (mristin):
# This module is private (it is emitted to ``src/``, never installed alongside
# the public headers in ``include/``), included only by ``verification.cpp``.
# It provides ``JsonValueVerificator``, a hand-written ``impl::IVerificator``
# (see ``verification.hpp``) which exhaustively walks a ``nlohmann::json``
# value with an explicit, runtime stack -- unlike every other verificator in
# ``verification.cpp``, which is generated per property/class because the
# meta-model's own structure is static, the recursion depth of a JSON-able
# value is only known at runtime, so a single, generic, hand-written engine
# is used for every ``JSONValue``/``JSONArray``/``JSONObject[K]``-typed
# property alike, regardless of the meta-model.
#
# The content generated here does not depend on the meta-model
# (``symbol_table``) at all.

import io
from typing import List

from aas_core_codegen.common import Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_json_value_verificator_declaration() -> List[Stripped]:
    """Generate the declaration of ``JsonValueVerificator``."""
    return [
        Stripped(
            """\
/**
 * Specify the shape that the top-level JSON value itself is expected to
 * have, ``kAny`` if unconstrained.
 */
enum class JsonValueShape {
  kAny,
  kArray,
  kObject
};  // enum class JsonValueShape"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Exhaustively verify that a ``nlohmann::json`` value is JSON-able.
 *
 * A JSON-able value is, recursively, exactly as JSON itself is defined:
 * a boolean, a number, a string, an array of JSON-able values or an object
 * of JSON-able values with string keys -- in particular, ``null``, a binary
 * value and a discarded value are rejected, at any depth.
 *
 * We deliberately walk the value with an explicit stack instead of plain
 * recursion, since a JSON-able value's nesting depth is a run-time property
 * we know nothing about at code-generation time -- unlike every other
 * verificator in this module, which only ever needs to unroll the
 * meta-model's own, statically known structure.
 *
 * Every violation at every depth is reported, one at a time, mirroring
 * every other verificator in this module -- not just the first one.
 */
class JsonValueVerificator : public impl::IVerificator {{
 public:
{I}JsonValueVerificator(
{II}const nlohmann::json& value,
{II}JsonValueShape expected_shape
{I});

{I}JsonValueVerificator(const JsonValueVerificator& other);

{I}void Start() override;
{I}void Next() override;
{I}bool Done() const override;
{I}const Error& Get() const override;
{I}Error& GetMutable() override;
{I}long Index() const override;

{I}std::unique_ptr<impl::IVerificator> Clone() const override;

{I}~JsonValueVerificator() override = default;

 private:
{I}/**
{I} * \\brief Represent a single value queued for a shape check.
{I} *
{I} * ``value`` points into the JSON-able value passed to the constructor,
{I} * and is only valid as long as that value is alive -- mirroring how
{I} * every other verificator in this module only holds a reference/pointer
{I} * into the instance under verification, never a copy of it.
{I} */
{I}struct WorkItem {{
{II}const nlohmann::json* value;

{II}/**
{II} * Human-readable path to \\ref value, *e.g.*, ``$[2].foo``
{II} */
{II}std::wstring path;

{II}WorkItem(
{III}const nlohmann::json* a_value,
{III}std::wstring a_path
{II});
{I}}};  // struct WorkItem

{I}const nlohmann::json* value_;
{I}JsonValueShape expected_shape_;

{I}bool done_;
{I}long index_;
{I}std::unique_ptr<Error> error_;
{I}std::deque<WorkItem> stack_;

{I}/**
{I} * \\brief Advance the ``stack_`` until either a violation is found, or
{I} * the ``stack_`` is exhausted.
{I} */
{I}void Advance();
}};  // class JsonValueVerificator"""
        ),
    ]


def _generate_json_value_verificator_implementation() -> List[Stripped]:
    """Generate the implementation of ``JsonValueVerificator``."""
    return [
        Stripped(
            f"""\
JsonValueVerificator::WorkItem::WorkItem(
{I}const nlohmann::json* a_value,
{I}std::wstring a_path
) :
{I}value(a_value),
{I}path(std::move(a_path)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
JsonValueVerificator::JsonValueVerificator(
{I}const nlohmann::json& value,
{I}JsonValueShape expected_shape
) :
{I}value_(&value),
{I}expected_shape_(expected_shape),
{I}done_(false),
{I}index_(-1),
{I}error_(nullptr) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
JsonValueVerificator::JsonValueVerificator(
{I}const JsonValueVerificator& other
) :
{I}value_(other.value_),
{I}expected_shape_(other.expected_shape_),
{I}done_(other.done_),
{I}index_(other.index_),
{I}error_(
{II}other.error_ != nullptr
{III}? common::make_unique<Error>(*other.error_)
{III}: nullptr
{I}),
{I}stack_(other.stack_) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
void JsonValueVerificator::Start() {{
{I}done_ = false;
{I}index_ = -1;
{I}error_ = nullptr;
{I}stack_.clear();

{I}bool shape_ok = true;
{I}std::wstring shape_cause;

{I}switch (expected_shape_) {{
{II}case JsonValueShape::kArray:
{III}if (!value_->is_array()) {{
{IIII}shape_ok = false;
{IIII}shape_cause = L"Expected a JSON array, but got a value of "
{IIII}L"a different JSON type";
{III}}}
{III}break;
{II}case JsonValueShape::kObject:
{III}if (!value_->is_object()) {{
{IIII}shape_ok = false;
{IIII}shape_cause = L"Expected a JSON object, but got a value of "
{IIII}L"a different JSON type";
{III}}}
{III}break;
{II}default:
{III}// NOTE (mristin):
{III}// ``JsonValueShape::kAny`` does not constrain the top-level shape.
{III}break;
{I}}}

{I}if (!shape_ok) {{
{II}error_ = common::make_unique<Error>(shape_cause);
{II}++index_;
{II}return;
{I}}}

{I}stack_.emplace_back(value_, std::wstring(L"$"));
{I}Advance();
}}"""
        ),
        Stripped(
            f"""\
void JsonValueVerificator::Next() {{
{I}if (done_) {{
{II}throw std::logic_error(
{III}"You want to move past the end of a JsonValueVerificator."
{II});
{I}}}

{I}Advance();
}}"""
        ),
        Stripped(
            f"""\
void JsonValueVerificator::Advance() {{
{I}error_ = nullptr;

{I}while (!stack_.empty()) {{
{II}const WorkItem item(std::move(stack_.front()));
{II}stack_.pop_front();

{II}const nlohmann::json& value = *item.value;

{II}if (value.is_null() || value.is_binary() || value.is_discarded()) {{
{III}std::wstring message = common::Concat(
{IIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIII}L"an array or an object), but got a value of a different, "
{IIII}L"non-JSON-able type (possibly null) at the JSON path ",
{IIII}item.path
{III});

{III}error_ = common::make_unique<Error>(message);
{III}++index_;
{III}return;
{II}}}

{II}if (value.is_array()) {{
{III}size_t index = 0;
{III}for (const nlohmann::json& item_value : value) {{
{IIII}std::wstring child_path = common::Concat(
{IIIII}item.path,
{IIIII}L"[",
{IIIII}std::to_wstring(index),
{IIIII}L"]"
{IIII});

{IIII}stack_.emplace_back(&item_value, std::move(child_path));
{IIII}++index;
{III}}}
{II}}} else if (value.is_object()) {{
{III}for (const auto& item_kv : value.items()) {{
{IIII}std::wstring child_path = common::Concat(
{IIIII}item.path,
{IIIII}L".",
{IIIII}common::Utf8ToWstring(item_kv.key())
{IIII});

{IIII}stack_.emplace_back(&item_kv.value(), std::move(child_path));
{III}}}
{II}}}
{I}}}

{I}done_ = true;
}}"""
        ),
        Stripped(
            f"""\
bool JsonValueVerificator::Done() const {{
{I}return done_;
}}"""
        ),
        Stripped(
            f"""\
const Error& JsonValueVerificator::Get() const {{
{I}if (error_ == nullptr) {{
{II}throw std::logic_error(
{III}"You want to dereference a JsonValueVerificator "
{III}"which is done or not yet started."
{II});
{I}}}

{I}return *error_;
}}"""
        ),
        Stripped(
            f"""\
Error& JsonValueVerificator::GetMutable() {{
{I}if (error_ == nullptr) {{
{II}throw std::logic_error(
{III}"You want to dereference a JsonValueVerificator "
{III}"which is done or not yet started."
{II});
{I}}}

{I}return *error_;
}}"""
        ),
        Stripped(
            f"""\
long JsonValueVerificator::Index() const {{
{I}return index_;
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<impl::IVerificator> JsonValueVerificator::Clone() const {{
{I}return common::make_unique<JsonValueVerificator>(*this);
}}"""
        ),
    ]


def generate_header(library_namespace: Stripped) -> str:
    """Generate header for the exhaustive verification of JSON-able values."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.VERIFICATION_NAMESPACE}")

    include_guard_var = cpp_common.include_guard_var(
        Stripped(f"{namespace}::json_value_verification")
    )

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
#include "{include_prefix_path}/verification.hpp"

#pragma warning(push, 0)
#include <nlohmann/json.hpp>

#include <deque>
#include <memory>
#include <string>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(f"namespace {cpp_common.VERIFICATION_NAMESPACE} {{"),
        *_generate_json_value_verificator_declaration(),
        Stripped(f"}}  // namespace {cpp_common.VERIFICATION_NAMESPACE}"),
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


def generate_implementation(library_namespace: Stripped) -> str:
    """Generate implementation for the exhaustive verification of JSON-able values."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.VERIFICATION_NAMESPACE}")

    blocks = [
        cpp_common.WARNING,
        Stripped(
            """\
#include "json_value_verification.hpp"

#pragma warning(push, 0)
#include <stdexcept>
#include <utility>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        *_generate_json_value_verificator_implementation(),
        cpp_common.generate_namespace_closing(namespace),
        cpp_common.WARNING,
    ]

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
