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
 * Every violation at every depth is reported, one at a time, in the order of
 * a depth-first walk -- not just the first one -- mirroring every other
 * verificator in this module.
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
{I} * \\brief Represent one level of the depth-first walk.
{I} *
{I} * ``container`` points into the JSON-able value passed to the constructor,
{I} * and is only valid as long as that value is alive -- mirroring how
{I} * every other verificator in this module only holds a reference/pointer
{I} * into the instance under verification, never a copy of it.
{I} */
{I}struct Frame {{
{II}/**
{II} * Array or object whose children we are walking through
{II} */
{II}const nlohmann::json* container;

{II}/**
{II} * Child of \\ref container which we are currently looking at
{II} */
{II}nlohmann::json::const_iterator cursor;

{II}/**
{II} * \\brief Position of \\ref cursor within \\ref container.
{II} *
{II} * Only meaningful if \\ref container is an array. We have to track it
{II} * ourselves as ``nlohmann::json``'s iterators give us the key of
{II} * an object member, but not the index of an array item.
{II} */
{II}size_t index;

{II}Frame(
{III}const nlohmann::json* a_container,
{III}nlohmann::json::const_iterator a_cursor,
{III}size_t an_index
{II});
{I}}};  // struct Frame

{I}const nlohmann::json* value_;
{I}JsonValueShape expected_shape_;

{I}bool done_;
{I}long index_;
{I}std::unique_ptr<Error> error_;

{I}/**
{I} * \\brief Capture where the depth-first walk currently is.
{I} *
{I} * The stack doubles as the path to the value that we are currently
{I} * looking at -- the cursor of the i-th frame gives the i-th segment of
{I} * that path. We therefore have to iterate over the stack, which rules
{I} * out ``std::stack``.
{I} *
{I} * We deliberately use a deque instead of a vector. A deque never
{I} * invalidates the references to its elements when we push or pop at its
{I} * ends, so the walk can hold on to the top frame while it descends into
{I} * a child, whereas a vector would move every frame elsewhere as soon as
{I} * a push exhausted its capacity, leaving such a reference dangling.
{I} */
{I}std::deque<Frame> stack_;

{I}/**
{I} * \\brief Advance the walk until either a violation is found, or
{I} * the value has been exhaustively visited.
{I} */
{I}void Advance();

{I}/**
{I} * \\brief Move \\p frame on to the next child.
{I} *
{I} * The cursor and the index of a frame have to move in lockstep, so we
{I} * keep that in a single place.
{I} *
{I} * \\param frame to be moved on
{I} */
{I}static void StepOver(Frame& frame);

{I}/**
{I} * \\brief Materialize the path to the value that \\ref stack_ currently
{I} * points to.
{I} *
{I} * This is the only place where we allocate path segments, so that
{I} * a JSON-able value costs us no allocation at all.
{I} */
{I}iteration::Path CurrentPath() const;
}};  // class JsonValueVerificator"""
        ),
    ]


def _generate_json_value_verificator_implementation() -> List[Stripped]:
    """Generate the implementation of ``JsonValueVerificator``."""
    return [
        Stripped(
            f"""\
namespace {{

/**
 * \\brief Check the shape of \\p value itself, disregarding the nested values.
 *
 * \\param value to be checked
 * \\return the cause of the violation, if any
 */
common::optional<std::wstring> CheckShallowly(
{I}const nlohmann::json& value
) {{
{I}if (value.is_null() || value.is_binary() || value.is_discarded()) {{
{II}return common::make_optional<std::wstring>(
{III}common::Concat(
{IIII}L"Expected a JSON-able value (a boolean, a number, a string, "
{IIII}L"an array or an object), but got a value of type: ",
{IIII}common::Utf8ToWstring(value.type_name())
{III})
{II});
{I}}}

{I}// NOTE (mristin):
{I}// JSON knows neither an infinity nor a not-a-number, so neither is
{I}// a JSON-able value, even though ``nlohmann::json`` will happily hold
{I}// one if it was constructed programmatically. This mirrors what the
{I}// jsonization refuses to serialize.
{I}if (value.is_number_float() && !std::isfinite(value.get<double>())) {{
{II}return common::make_optional<std::wstring>(
{III}common::Concat(
{IIII}L"Expected a JSON-able value, but got the number ",
{IIII}std::to_wstring(value.get<double>()),
{IIII}L", which is neither finite nor representable in JSON"
{III})
{II});
{I}}}

{I}return common::nullopt;
}}

}}  // namespace"""
        ),
        Stripped(
            f"""\
JsonValueVerificator::Frame::Frame(
{I}const nlohmann::json* a_container,
{I}nlohmann::json::const_iterator a_cursor,
{I}size_t an_index
) :
{I}container(a_container),
{I}cursor(a_cursor),
{I}index(an_index) {{
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
iteration::Path JsonValueVerificator::CurrentPath() const {{
{I}iteration::Path path;

{I}for (const Frame& frame : stack_) {{
{II}if (frame.container->is_array()) {{
{III}path.segments.emplace_back(
{IIII}common::make_unique<iteration::IndexSegment>(frame.index)
{III});
{II}}} else {{
{III}path.segments.emplace_back(
{IIII}common::make_unique<iteration::KeySegment>(
{IIIII}common::Utf8ToWstring(frame.cursor.key())
{IIII})
{III});
{II}}}
{I}}}

{I}return path;
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
{IIII}shape_cause = common::Concat(
{IIIII}L"Expected a JSON array, but got a value of type: ",
{IIIII}common::Utf8ToWstring(value_->type_name())
{IIII});
{III}}}
{III}break;
{II}case JsonValueShape::kObject:
{III}if (!value_->is_object()) {{
{IIII}shape_ok = false;
{IIII}shape_cause = common::Concat(
{IIIII}L"Expected a JSON object, but got a value of type: ",
{IIIII}common::Utf8ToWstring(value_->type_name())
{IIII});
{III}}}
{III}break;
{II}default:
{III}// NOTE (mristin):
{III}// ``JsonValueShape::kAny`` does not constrain the top-level shape.
{III}break;
{I}}}

{I}if (!shape_ok) {{
{II}error_ = common::make_unique<Error>(std::move(shape_cause));
{II}++index_;
{II}return;
{I}}}

{I}common::optional<std::wstring> cause(CheckShallowly(*value_));
{I}if (cause.has_value()) {{
{II}error_ = common::make_unique<Error>(std::move(*cause));
{II}++index_;
{II}return;
{I}}}

{I}if (value_->is_array() || value_->is_object()) {{
{II}stack_.emplace_back(value_, value_->cbegin(), 0);
{I}}}

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
void JsonValueVerificator::StepOver(Frame& frame) {{
{I}++frame.cursor;
{I}++frame.index;
}}"""
        ),
        Stripped(
            f"""\
void JsonValueVerificator::Advance() {{
{I}error_ = nullptr;

{I}while (!stack_.empty()) {{
{II}// NOTE (mristin):
{II}// A deque never invalidates the references to its elements when we push
{II}// or pop at its ends, so this reference survives the descent further
{II}// below, which pushes a frame. Mind that it does *not* survive
{II}// the ``pop_back`` -- that erases the very frame it refers to.
{II}Frame& frame = stack_.back();

{II}if (frame.cursor == frame.container->cend()) {{
{III}// We exhausted this array or object, so we resume in its parent,
{III}// stepping over the very array or object that we just finished.
{III}stack_.pop_back();

{III}if (!stack_.empty()) {{
{IIII}StepOver(stack_.back());
{III}}}

{III}continue;
{II}}}

{II}const nlohmann::json& value = *frame.cursor;

{II}common::optional<std::wstring> cause(CheckShallowly(value));
{II}if (cause.has_value()) {{
{III}error_ = common::make_unique<Error>(std::move(*cause));
{III}error_->path = CurrentPath();

{III}// NOTE (mristin):
{III}// We step over the offending value immediately so that the next
{III}// call to Advance() continues with the value after it, instead of
{III}// reporting the very same violation over and over again.
{III}StepOver(frame);

{III}++index_;
{III}return;
{II}}}

{II}if (value.is_array() || value.is_object()) {{
{III}stack_.emplace_back(&value, value.cbegin(), 0);
{III}continue;
{II}}}

{II}StepOver(frame);
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
#include <cmath>
#include <stdexcept>
#include <string>
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
