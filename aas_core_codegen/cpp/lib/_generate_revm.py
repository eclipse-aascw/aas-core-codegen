"""Generate code of a virtual machine for matching regular expressions."""

import io

from icontract import ensure

from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
    INDENT7 as IIIIIII,
    INDENT8 as IIIIIIII,
)

# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(library_namespace: Stripped) -> str:
    """Generate header of a virtual machine for matching regular expressions."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.REVM_NAMESPACE}")

    include_guard_var = cpp_common.include_guard_var(namespace)

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            """\
#pragma warning(push, 0)
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            f"""\
/**
 * \\defgroup {cpp_common.REVM_NAMESPACE} Match regular expressions using a multi-threaded virtual machine.
 *
 * The implementation in the standard library has exponential time complexity, so it was
 * a major blocker for most of the practical inputs. For example, see this bug report:
 * https://gcc.gnu.org/bugzilla/show_bug.cgi?id=93502
 *
 * This implementation is based on Ken Thompson's approach which uses a virtual
 * machine to match regular expressions. The original technique has been
 * published in:
 * Thompson, K., "Regular expression search algorithm", ACM 11(6) (June 1968)
 *
 * We followed a very clear and concise blog post which described in detail:
 * https://swtch.com/~rsc/regexp/regexp2.html
 *
 * The ideas for additional instructions were taken from:
 * https://www.codeproject.com/Articles/5256833/Regex-as-a-Tiny-Threaded-Virtual-Machine
 * @{{
 */
namespace {cpp_common.REVM_NAMESPACE} {{

enum class InstructionKind : std::uint8_t {{
{I}Char,
{I}Set,
{I}NotSet,
{I}Any,
{I}Match,
{I}Jump,
{I}Split,
{I}End
}};

/**
 * Represent an instruction of the virtual machine.
 */
struct Instruction {{
{I}// NOTE (mristin):
{I}// We avoid RTTI for performance reasons, and use our own enumerator instead.
{I}virtual InstructionKind kind() const = 0;

{I}virtual ~Instruction() = default;
}};

/**
 * Match a single character.
 *
 * If the character on the String Pointer does not match the `character`, stop this
 * thread as it failed. Otherwise, move the String Pointer to the next character,
 * and the Program Counter to the next instruction.
 */
struct InstructionChar : Instruction {{
{I}wchar_t character;

{I}explicit InstructionChar(wchar_t a_character);
{I}InstructionKind kind() const override;
{I}~InstructionChar() override = default;
}};

std::string to_string(const InstructionChar& instruction);

/**
 * Define a character range.
 */
struct Range {{
{I}wchar_t first;
{I}wchar_t last;

{I}Range(wchar_t a_first, wchar_t a_last);
}};

std::string to_string(const Range& range);

/**
 * Check whether the character is in any of the given character ranges.
 *
 * @return true if the character is in any of the ranges
 */
bool CharacterInRanges(
{I}const std::vector<Range>& ranges,
{I}wchar_t character
);

/**
 * Match a set of characters.
 *
 * If the character on the String Pointer *is not* in the given set, stop this
 * thread as it failed. Otherwise, move the String Pointer to the next character,
 * and the Program Counter to the next instruction.
 */
struct InstructionSet : Instruction {{
{I}std::vector<Range> ranges;

{I}explicit InstructionSet(std::vector<Range> a_ranges);
{I}InstructionKind kind() const override;
{I}~InstructionSet() override = default;
}};

std::string to_string(const InstructionSet& instruction);

/**
 * Match an out-of-set character.
 *
 * If the character on the String Pointer *is* in the given set, stop this
 * thread as it failed. Otherwise, move the String Pointer to the next character,
 * and the Program Counter to the next instruction.
 */
struct InstructionNotSet : Instruction {{
{I}std::vector<Range> ranges;

{I}explicit InstructionNotSet(std::vector<Range> a_ranges);
{I}InstructionKind kind() const override;
{I}~InstructionNotSet() override = default;
}};

std::string to_string(const InstructionNotSet& instruction);

/**
 * Match any character.
 */
struct InstructionAny : Instruction {{
{I}InstructionKind kind() const override;
{I}~InstructionAny() override = default;
}};

std::string to_string(const InstructionAny&);

/**
 * Stop this thread and signal that we found a match.
 */
struct InstructionMatch : Instruction {{
{I}InstructionKind kind() const override;
{I}~InstructionMatch() override = default;
}};

std::string to_string(const InstructionMatch&);

/**
 * Jump to the indicated position in the program.
 */
struct InstructionJump : Instruction {{
{I}size_t target;

{I}explicit InstructionJump(size_t a_target);
{I}InstructionKind kind() const override;
{I}~InstructionJump() override = default;
}};

std::string to_string(const InstructionJump& instruction);

/**
 * Split the program in two threads, both jumping to different locations. The string
 * pointer is kept as-is.
 */
struct InstructionSplit : Instruction {{
{I}size_t first_target;
{I}size_t second_target;

{I}explicit InstructionSplit(size_t a_first_target, size_t a_second_target);
{I}InstructionKind kind() const override;
{I}~InstructionSplit() override = default;
}};

std::string to_string(const InstructionSplit& instruction);

/**
 * Match the end-of-input.
 */
struct InstructionEnd : Instruction {{
{I}InstructionKind kind() const override;
{I}~InstructionEnd() override = default;
}};

std::string to_string(const InstructionEnd&);

std::string to_string(const Instruction& instruction);

std::string to_string(
{I}const std::vector<std::unique_ptr<Instruction> >& instructions
);

/**
 * Try to match the program against the text.
 * @return true if the text matches
 */
bool Match(
{I}const std::vector<std::unique_ptr<Instruction> >& program,
{I}const std::wstring& text
);

}}  // namespace {cpp_common.REVM_NAMESPACE}
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


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    library_namespace: Stripped,
) -> str:
    """Generate implementation of a virtual machine for matching regular expressions."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.REVM_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/revm.hpp"

#pragma warning(push, 0)
#include <algorithm>
#include <iomanip>
#include <sstream>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        Stripped(
            f"""\
/**
 * Represent the character such that it can be printed in the console.
 *
 * To that end, we escape the character if it is out of the printable ASCII set.
 *
 * This function is mostly meant for debugging purposes.
 */
std::string RepresentWCharacter(wchar_t character) {{
{I}switch (character) {{
{II}case L'\\\\':return "\\\\\\\\";
{II}case L'"':return "\\\\\\"";
{II}case L'\\'':return "\\\\'";
{II}case L'\\t':return "\\\\t";
{II}case L'\\n':return "\\\\n";
{II}case L'\\r':return "\\\\r";
{II}default: break;
{I}}}

{I}if (26 <= character && character <= 126) {{
{II}return std::string(1, static_cast<char>(character));
{I}}}

{I}static const char* digits = "0123456789ABCDEF";
{I}size_t digit_count = sizeof(wchar_t) * 2;

{I}std::string result;
{I}result.resize(digit_count + 2);
{I}result[0] = L'\\\\';
{I}result[1] = L'u';

{I}for (size_t i = 0, j = (digit_count - 1) * 4; i < digit_count; ++i, j -= 4) {{
{II}const size_t digit_i = (character >> j) & 0x0f;
{II}result[i + 2] = digits[digit_i];
{I}}}

{I}return result;
}}

/**
 * Represent the wide string for debugging purposes where it is printed to the console.
 *
 * To that end, we escape the individual characters if they are out of printable ASCII
 * set.
 */
std::string RepresentWString(const std::wstring& text) {{
{I}std::vector<std::string> parts;
{I}parts.reserve(text.size());
{I}for (const wchar_t character : text) {{
{II}parts.emplace_back(RepresentWCharacter(character));
{I}}}

{I}size_t size = 0;
{I}for (const std::string& part : parts) {{
{II}size += part.size();
{I}}}

{I}std::string result;
{I}result.reserve(size);
{I}for (const std::string& part : parts) {{
{II}result.append(part);
{I}}}
{I}return result;
}}

InstructionChar::InstructionChar(
{I}wchar_t a_character
) :
{I}character(a_character) {{
{I}// Intentionally empty.
}}

InstructionKind InstructionChar::kind() const {{
{I}return InstructionKind::Char;
}}

std::string to_string(const InstructionChar& instruction) {{
{I}return common::Concat(
{II}"char '",
{II}RepresentWCharacter(instruction.character),
{II}"'"
{I});
}}

Range::Range(
{I}wchar_t a_first,
{I}wchar_t a_last
) :
{I}first(a_first),
{I}last(a_last) {{
{I}// NOTE (mristin):
{I}// We are aware that exceptions in constructors should be avoided to prevent
{I}// bug related to uninitialized object state. However, in this case, we do not
{I}// see any risk for such a mistake.
{I}if (a_first > a_last) {{
{II}throw std::invalid_argument(
{III}common::Concat(
{IIII}"The first character in a character range, ",
{IIII}RepresentWCharacter(a_first),
{IIII}", is larger than the last character in the range, ",
{IIII}RepresentWCharacter(a_last)
{III})
{II});
{I}}}
}}

std::string to_string(const Range& range) {{
{I}if (range.first == range.last) {{
{II}return RepresentWCharacter(range.first);
{I}}}

{I}return common::Concat(
{II}RepresentWCharacter(range.first),
{II}"-",
{II}RepresentWCharacter(range.last)
{I});
}}

InstructionSet::InstructionSet(
{I}std::vector<Range> a_ranges
) :
{I}ranges(std::move(a_ranges)) {{
{I}// NOTE (mristin):
{I}// We are aware that exceptions in constructors should be avoided to prevent
{I}// bug related to uninitialized object state. However, in this case, we do not
{I}// see any risk for such a mistake.
{I}if (ranges.empty()) {{
{II}throw std::invalid_argument(
{III}"Unexpected NotSet instruction with empty ranges"
{II});
{I}}}

{I}for (size_t i = 1; i < ranges.size(); ++i) {{
{II}if (ranges[i - 1].last >= ranges[i].first) {{
{III}throw std::invalid_argument(
{IIII}common::Concat(
{IIIII}"The ranges for an InstructionSet are unexpectedly either "
{IIIII}"not sorted or overlapping. The range at index ",
{IIIII}std::to_string(i - 1),
{IIIII}" is ",
{IIIII}to_string(ranges[i - 1]),
{IIIII}" and the range at index ",
{IIIII}std::to_string(i),
{IIIII}" is ",
{IIIII}to_string(ranges[i])
{IIII})
{III});
{II}}}
{I}}}
}}

InstructionKind InstructionSet::kind() const {{
{I}return InstructionKind::Set;
}}

std::string to_string(const InstructionSet& instruction) {{
{I}std::stringstream ss;
{I}ss << "set '";

{I}for (const auto& range : instruction.ranges) {{
{II}ss << to_string(range);
{I}}}

{I}ss << "'";
{I}return ss.str();
}}

InstructionNotSet::InstructionNotSet(
{I}std::vector<Range> a_ranges
) :
{I}ranges(std::move(a_ranges)) {{
{I}// NOTE (mristin):
{I}// We are aware that exceptions in constructors should be avoided to prevent
{I}// bug related to uninitialized object state. However, in this case, we do not
{I}// see any risk for such a mistake.
{I}if (ranges.empty()) {{
{II}throw std::invalid_argument(
{III}"Unexpected NotSet instruction with empty ranges"
{II});
{I}}}

{I}for (size_t i = 1; i < ranges.size(); ++i) {{
{II}if (ranges[i - 1].last >= ranges[i].first) {{
{III}throw std::invalid_argument(
{IIII}common::Concat(
{IIIII}"The ranges for an InstructionNotSet are unexpectedly either "
{IIIII}"not sorted or overlapping. The range at index ",
{IIIII}std::to_string(i - 1),
{IIIII}" is ",
{IIIII}to_string(ranges[i - 1]),
{IIIII}" and the range at index ",
{IIIII}std::to_string(i),
{IIIII}" is ",
{IIIII}to_string(ranges[i])
{IIII})
{III});
{II}}}
{I}}}
}}

InstructionKind InstructionNotSet::kind() const {{
{I}return InstructionKind::NotSet;
}}

std::string to_string(const InstructionNotSet& instruction) {{
{I}std::stringstream ss;
{I}ss << "not-set '";

{I}for (const auto& range : instruction.ranges) {{
{II}ss << to_string(range);
{I}}}

{I}ss << "'";
{I}return ss.str();
}}

InstructionKind InstructionAny::kind() const {{
{I}return InstructionKind::Any;
}}

std::string to_string(const InstructionAny&) {{
{I}return "any";
}}

InstructionKind InstructionMatch::kind() const {{
{I}return InstructionKind::Match;
}}

std::string to_string(const InstructionMatch&) {{
{I}return "match";
}}

InstructionJump::InstructionJump(
{I}size_t a_target
) :
{I}target(a_target) {{
{I}// Intentionally empty.
}}

InstructionKind InstructionJump::kind() const {{
{I}return InstructionKind::Jump;
}}

std::string to_string(const InstructionJump& instruction) {{
{I}return common::Concat(
{II}"jump ",
{II}std::to_string(instruction.target)
{I});
}}

InstructionSplit::InstructionSplit(
{I}size_t a_first_target,
{I}size_t a_second_target
) :
{I}first_target(a_first_target),
{I}second_target(a_second_target) {{
{I}// Intentionally empty.
}}

InstructionKind InstructionSplit::kind() const {{
{I}return InstructionKind::Split;
}}

std::string to_string(const InstructionSplit& instruction) {{
{I}return common::Concat(
{II}"split ",
{III}std::to_string(instruction.first_target),
{III}", ",
{III}std::to_string(instruction.second_target)
{I});
}}

InstructionKind InstructionEnd::kind() const {{
{I}return InstructionKind::End;
}}

std::string to_string(const InstructionEnd&) {{
{I}return "end";
}}

std::string to_string(const Instruction& instruction) {{
{I}switch (instruction.kind()) {{
{II}case InstructionKind::Char:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionChar&
{IIII}>(instruction)
{III});

{II}case InstructionKind::Set:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionSet&
{IIII}>(instruction)
{III});

{II}case InstructionKind::NotSet:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionNotSet&
{IIII}>(instruction)
{III});

{II}case InstructionKind::Any:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionAny&
{IIII}>(instruction)
{III});

{II}case InstructionKind::Match:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionMatch&
{IIII}>(instruction)
{III});

{II}case InstructionKind::Jump:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionJump&
{IIII}>(instruction)
{III});

{II}case InstructionKind::Split:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionSplit&
{IIII}>(instruction)
{III});

{II}case InstructionKind::End:
{III}return to_string(
{IIII}static_cast<   // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIII}const InstructionEnd&
{IIII}>(instruction)
{III});

{II}default:
{III}throw std::logic_error(
{IIII}common::Concat(
{IIIII}"Unhandled instruction kind: ",
{IIIII}std::to_string(
{IIIIII}static_cast<std::uint8_t>(instruction.kind())
{IIIII})
{IIII})
{III});
{I}}}
}}

std::string to_string(
{I}const std::vector<std::unique_ptr<Instruction> >& instructions
) {{
{I}std::stringstream ss;
{I}for (size_t i = 0; i < instructions.size(); ++i) {{
{II}ss
{III}<< std::setw(4) << i << ": "
{III}<< to_string(*instructions[i]) << std::endl;
{I}}}

{I}return ss.str();
}}

bool CharacterInRanges(
{I}const std::vector<Range>& ranges,
{I}wchar_t character
) {{
{I}if (ranges.empty()) {{
{II}return false;
{I}}}

{I}if (ranges.size() == 1) {{
{II}return (ranges[0].first <= character && character <= ranges[0].last);
{I}}}

{I}// Binary search
{I}size_t begin = 0;
{I}size_t end = ranges.size();

{I}while (true) {{
{II}if (begin == end) {{
{III}return false;
{II}}}

{II}// NOTE (mristin):
{II}// Most implementations of the binary search are buggy, see:
{II}// https://en.wikipedia.org/wiki/Binary_search_algorithm#Implementation_issues.
{II}//
{II}// We try to avert some of the bugs by explicitly handling the case where there
{II}// are at most 3 elements in the segment, so we stop here instead of proceeding
{II}// recursively.
{II}if (end - begin <= 3) {{
{III}for (size_t i = begin; i < end; ++i) {{
{IIII}const Range& range = ranges[i];
{IIII}if (range.first <= character && character <= range.last) {{
{IIIII}return true;
{IIII}}}
{III}}}
{III}return false;
{II}}}

{II}const size_t middle = (begin + end) / 2;
{II}const Range& range = ranges[middle];
{II}if (character < range.first) {{
{III}end = middle;
{II}}} else if (character > range.last) {{
{III}begin = middle;
{II}}} else {{
{III}return true;
{II}}}
{I}}}
}}

/**
 * Keep track of the threads currently being executed.
 */
class ThreadList {{
 public:
{I}explicit ThreadList(size_t program_size) {{
{II}has_.resize(program_size, false);
{II}items_.reserve(program_size);
{I}}}

{I}/**
{I} * Add a new thread for the given program counter if it is not already in the list.
{I} */
{I}void Spawn(size_t program_counter) {{
{II}#ifdef DEBUG
{II}if (program_counter >= has_.size()) {{
{III}throw std::invalid_argument(
{IIII}common::Concat(
{IIIII}"Unexpected spawning of a thread at the program counter ",
{IIIII}std::to_string(program_counter),
{IIIII}" since the program size was indicated to be ",
{IIIII}std::to_string(has_.size())
{IIII})
{III});
{II}}}
{II}#endif

{II}if (has_[program_counter]) {{
{III}return;
{II}}}

{II}has_[program_counter] = true;
{II}items_.push_back(program_counter);
{I}}}

{I}bool Empty() const {{
{II}return items_.empty();
{I}}}

{I}/**
{I} * Pop the thread from the back, returning its program counter.
{I} *
{I} * The order of the threads is not guaranteed.
{I} */
{I}size_t Pop() {{
{II}#ifdef DEBUG
{II}if (items_.empty()) {{
{III}throw std::logic_error(
{IIII}"You tried to pop from an empty thread list."
{IIII});
{II}}}
{II}#endif

{II}const size_t program_counter = items_.back();
{II}items_.pop_back();
{II}has_[program_counter] = false;
{II}return program_counter;
{I}}}

{I}/**
{I} * Clear the thread list, keeping its memory capacity.
{I} */
{I}void Clear() {{
{II}std::fill(has_.begin(), has_.end(), false);
{II}items_.clear();
{I}}}

{I}/**
{I} * Return the program counters corresponding to the spawned threads.
{I} */
{I}const std::vector<size_t>& Items() const {{
{II}return items_;
{I}}};

 private:
{I}/**
{I} * Keep track of the program counters corresponding to the threads so that we can
{I} * avoid the duplicate threads.
{I} */
{I}std::vector<bool> has_;

{I}/**
{I} * Keep track of the active threads.
{I} */
{I}std::vector<size_t> items_;
}};

std::string to_string(const ThreadList& thread_list) {{
{I}if (thread_list.Empty()) {{
{II}return "[]";
{I}}}

{I}std::vector<size_t> items(thread_list.Items());
{I}std::sort(items.begin(), items.end());

{I}std::stringstream ss;
{I}ss << "[";
{I}ss << std::to_string(items[0]);

{I}for (size_t i = 1; i < items.size(); ++i) {{
{II}ss << ", " << items[i];
{I}}}
{I}ss << "]";

{I}return ss.str();
}}

/**
 * Try to match the program against the text.
 *
 * @return true if the text matches
 */
bool Match(
{I}const std::vector<std::unique_ptr<Instruction> >& program,
{I}const std::wstring& text
) {{
{I}if (program.empty()) {{
{II}return false;
{I}}}

{I}// NOTE (mristin):
{I}// We validate at the beginning so that we can avoid checks in
{I}// the instruction loops.
{I}for (size_t i = 0; i < program.size(); ++i) {{
{II}const Instruction& instruction = *program[i];

{II}switch (instruction.kind()) {{
{III}case InstructionKind::Jump: {{
{IIII}const auto& instruction_jump(
{IIIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIII}const InstructionJump&
{IIIII}>(
{IIIIII}instruction
{IIIII})
{IIII});

{IIII}if (instruction_jump.target >= program.size()) {{
{IIIII}throw std::invalid_argument(
{IIIIII}common::Concat(
{IIIIIII}"Unexpected jump beyond the end of the program. Program has ",
{IIIIIII}std::to_string(program.size()),
{IIIIIII}" instruction(s), but the instruction ",
{IIIIIII}std::to_string(i),
{IIIIIII}" wants to jump to ",
{IIIIIII}std::to_string(instruction_jump.target)
{IIIIII})
{IIIII});
{IIII}}}
{IIII}break;
{III}}}

{III}case InstructionKind::Split: {{
{IIII}const auto& instruction_split(
{IIIII}static_cast<  // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIII}const InstructionSplit&
{IIIII}>(
{IIIIII}instruction
{IIIII})
{IIII});

{IIII}if (instruction_split.first_target >= program.size()) {{
{IIIII}throw std::invalid_argument(
{IIIIII}common::Concat(
{IIIIIII}"Unexpected split & jump beyond the end of the program. Program has ",
{IIIIIII}std::to_string(program.size()),
{IIIIIII}" instruction(s), but the instruction ",
{IIIIIII}std::to_string(i),
{IIIIIII}" wants to split and make the first jump to ",
{IIIIIII}std::to_string(instruction_split.first_target)
{IIIIII})
{IIIII});
{IIII}}}

{IIII}if (instruction_split.second_target >= program.size()) {{
{IIIII}throw std::invalid_argument(
{IIIIII}common::Concat(
{IIIIIII}"Unexpected split & jump beyond the end of the program. Program has ",
{IIIIIII}std::to_string(program.size()),
{IIIIIII}" instruction(s), but the instruction ",
{IIIIIII}std::to_string(i),
{IIIIIII}" wants to split and make the second jump to ",
{IIIIIII}std::to_string(instruction_split.second_target)
{IIIIII})
{IIIII});
{IIII}}}

{IIII}break;
{III}}}

{III}default:
{IIII}continue;
{II}}}
{I}}}

{I}// NOTE (mristin):
{I}// See: https://swtch.com/~rsc/regexp/regexp2.html,
{I}// Section "Thompson's Implementation".

{I}std::unique_ptr<ThreadList> clist(common::make_unique<ThreadList>(program.size()));
{I}std::unique_ptr<ThreadList> nlist(common::make_unique<ThreadList>(program.size()));

{I}clist->Spawn(0);

{I}for (const wchar_t character : text) {{
{II}#ifdef DEBUG
{II}if (!nlist->Empty()) {{
{III}throw std::logic_error(
{IIII}"Expected the list of next-to-be-executed threads to be empty, "
{IIII}"but it was not."
{III});
{II}}}
{II}#endif

{II}while (!clist->Empty()) {{
{III}const size_t program_counter = clist->Pop();

{III}#ifdef DEBUG
{III}if (program_counter >= program.size()) {{
{IIII}throw std::logic_error(
{IIIII}common::Concat(
{IIIIII}"Unexpected program counter beyond the program. The program size was ",
{IIIIII}std::to_string(program.size()),
{IIIIII}", while the program counter of a thread was ",
{IIIIII}std::to_string(program_counter)
{IIIII})
{IIII});
{III}}}
{III}#endif

{III}const Instruction& instruction = *program[program_counter];

{III}switch (instruction.kind()) {{
{IIII}case InstructionKind::Char: {{
{IIIII}const auto& instruction_char(
{IIIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIIII}const InstructionChar&
{IIIIII}>(instruction)
{IIIII});

{IIIII}if (character != instruction_char.character) {{
{IIIIII}// The matching failed for this thread.
{IIIIII}break;
{IIIII}}}

{IIIII}nlist->Spawn(program_counter + 1);
{IIIII}break;
{IIII}}}

{IIII}case InstructionKind::Set: {{
{IIIII}const auto& instruction_set(
{IIIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIIII}const InstructionSet&
{IIIIII}>(instruction)
{IIIII});

{IIIII}if (!CharacterInRanges(instruction_set.ranges, character)) {{
{IIIIII}// The matching failed for this thread.
{IIIIII}break;
{IIIII}}}

{IIIII}nlist->Spawn(program_counter + 1);
{IIIII}break;
{IIII}}}

{IIII}case InstructionKind::NotSet: {{
{IIIII}const auto& instruction_not_set(
{IIIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIIII}const InstructionNotSet&
{IIIIII}>(instruction)
{IIIII});

{IIIII}if (CharacterInRanges(instruction_not_set.ranges, character)) {{
{IIIIII}// The matching failed for this thread.
{IIIIII}break;
{IIIII}}}

{IIIII}nlist->Spawn(program_counter + 1);
{IIIII}break;
{IIII}}}

{IIII}case InstructionKind::Any: {{
{IIIII}// NOTE (mristin):
{IIIII}// We simply proceed to the next instruction at the next character without
{IIIII}// any checks.
{IIIII}nlist->Spawn(program_counter + 1);
{IIIII}break;
{IIII}}}

{IIII}case InstructionKind::Match:
{IIIII}return true;

{IIII}case InstructionKind::Jump: {{
{IIIII}const auto& instruction_jump(
{IIIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIIII}const InstructionJump&
{IIIIII}>(instruction)
{IIIII});

{IIIII}clist->Spawn(instruction_jump.target);
{IIIII}break;
{IIII}}}

{IIII}case InstructionKind::Split: {{
{IIIII}const auto& instruction_split(
{IIIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIIII}const InstructionSplit&
{IIIIII}>(instruction)
{IIIII});

{IIIII}clist->Spawn(instruction_split.first_target);
{IIIII}clist->Spawn(instruction_split.second_target);
{IIIII}break;
{IIII}}}

{IIII}case InstructionKind::End: {{
{IIIII}// The matching failed for this thread as we have just consumed
{IIIII}// a character.
{IIIII}break;
{IIII}}}

{IIII}default:
{IIIII}throw std::logic_error(
{IIIIII}common::Concat(
{IIIIIII}"Unhandled instruction kind: ",
{IIIIIII}std::to_string(
{IIIIIIII}static_cast<std::uint8_t>(instruction.kind())
{IIIIIII})
{IIIIII})
{IIIII});
{III}}}
{II}}}

{II}std::swap(clist, nlist);
{II}nlist->Clear();
{I}}}

{I}// NOTE (mristin):
{I}// We need to process any pending jumps, splits and matches even tough there are
{I}// no more characters to consume.
{I}while (!clist->Empty()) {{
{II}const size_t program_counter = clist->Pop();

{II}#ifdef DEBUG
{II}if (program_counter >= program.size()) {{
{III}throw std::logic_error(
{IIII}common::Concat(
{IIIII}"Unexpected program counter beyond the program. The program size was ",
{IIIII}std::to_string(program.size()),
{IIIII}", while the program counter of a thread was ",
{IIIII}std::to_string(program_counter)
{IIII})
{III});
{II}}}
{II}#endif

{II}const Instruction& instruction = *program[program_counter];

{II}switch (instruction.kind()) {{
{III}case InstructionKind::Char: {{ // NOLINT(bugprone-branch-clone)
{IIII}// We reached the end-of-input so there are no characters to be matched.
{IIII}// This thread needs therefore to die.
{IIII}break;
{III}}}

{III}case InstructionKind::Set: {{
{IIII}// We reached the end-of-input so there are no character sets to be matched.
{IIII}// This thread needs therefore to die.
{IIII}break;
{III}}}

{III}case InstructionKind::NotSet: {{
{IIII}// We reached the end-of-input so there are no character sets to be matched.
{IIII}// This thread needs therefore to die.
{IIII}break;
{III}}}

{III}case InstructionKind::Any: {{
{IIII}// We reached the end-of-input so there are no characters to be matched.
{IIII}// This thread needs therefore to die.
{IIII}break;
{III}}}

{III}case InstructionKind::Match:
{IIII}return true;

{III}case InstructionKind::Jump: {{
{IIII}const auto& instruction_jump(
{IIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIII}const InstructionJump&
{IIIII}>(instruction)
{IIII});

{IIII}clist->Spawn(instruction_jump.target);
{IIII}break;
{III}}}

{III}case InstructionKind::Split: {{
{IIII}const auto& instruction_split(
{IIIII}static_cast< // NOLINT(cppcoreguidelines-pro-type-static-cast-downcast)
{IIIIII}const InstructionSplit&
{IIIII}>(instruction)
{IIII});

{IIII}clist->Spawn(instruction_split.first_target);
{IIII}clist->Spawn(instruction_split.second_target);
{IIII}break;
{III}}}

{III}case InstructionKind::End: {{
{IIII}// We reached the end-of-input so we match and move to the next instruction.
{IIII}clist->Spawn(program_counter + 1);
{IIII}break;
{III}}}

{III}default:
{IIII}throw std::logic_error(
{IIIII}common::Concat(
{IIIIII}"Unhandled instruction kind: ",
{IIIIII}std::to_string(
{IIIIIII}static_cast<std::uint8_t>(instruction.kind())
{IIIIII})
{IIIII})
{IIII});
{II}}}
{I}}}

{I}return false;
}}"""
        ),
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
