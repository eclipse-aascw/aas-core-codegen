"""Generate code to specify regular expressions."""
import io
from typing import Tuple, Optional, Union, List, Mapping, TextIO

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    indent_but_first_line,
    Error,
    assert_never,
)
from aas_core_codegen.cpp import common as cpp_common, naming as cpp_naming
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import revm as intermediate_revm
from aas_core_codegen.parse import retree as parse_retree, tree as parse_tree

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
    """Generate header to specify regular expressions."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.PATTERN_NAMESPACE}")

    fully_qualified_match_function = Stripped(
        f"{library_namespace}::{cpp_common.REVM_NAMESPACE}::Match"
    )

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
#include "{include_prefix_path}/revm.hpp"

#pragma warning(push, 0)
#include <memory>
#include <vector>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            f"""\
/**
 * \\defgroup {cpp_common.PATTERN_NAMESPACE} Provide patterns to be matched using a multi-threaded virtual machine.
 *
 * The instructions should be supplied to {fully_qualified_match_function}. While
 * we could have theoretically included this code in verification, we decided to keep
 * it separate for readability. You are not expected to use this module directly.
 * @{{
 */
namespace {cpp_common.PATTERN_NAMESPACE} {{"""
        ),
    ]

    for verification in symbol_table.verification_functions:
        if not isinstance(verification, intermediate.PatternVerification):
            continue

        pattern_name = cpp_naming.constant_name(
            Identifier(f"{verification.name}_program")
        )

        blocks.append(
            Stripped(
                f"""\
extern const std::vector<
{I}std::unique_ptr<revm::Instruction>
> {pattern_name};"""
            )
        )

    blocks.extend(
        [
            Stripped(
                f"""\
}}  // namespace {cpp_common.PATTERN_NAMESPACE}
/**@}}*/"""
            ),
            cpp_common.generate_namespace_closing(library_namespace),
            cpp_common.WARNING,
            Stripped(f"#endif  // {include_guard_var}"),
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


class _RegexRenderer(parse_retree.Renderer):
    """
    Render the regular expressions for C++ ``std::wregex``.

    In contrast to :py:class:`parse_retree.Renderer`, we also render
    the :py:class:`parse_retree.Char` as we need to cover the granularity of a single
    character in this module.
    """

    def char_to_str_and_escape_or_encode_if_necessary(
        self, node: parse_retree.Char, escaping: Mapping[str, str]
    ) -> List[Union[str, parse_tree.FormattedValue]]:
        """Convert the ``node`` to a string, and escape and/or encode appropriately."""
        if not node.explicitly_encoded:
            escaped = escaping.get(node.character, None)
            if escaped is not None:
                result: List[Union[str, parse_tree.FormattedValue]] = [escaped]
            else:
                result = [node.character]

            return result
        else:
            code = ord(node.character)

            if code <= 255:
                return [f"\\x{code:02x}"]
            elif code <= 65535:
                return [f"\\u{code:04x}"]
            else:
                return [f"\\U{code:08x}"]

    def transform_char(
        self, node: parse_retree.Char
    ) -> List[Union[str, parse_tree.FormattedValue]]:
        return self.char_to_str_and_escape_or_encode_if_necessary(
            node=node, escaping=parse_retree.Renderer._ESCAPING_IN_CHARACTER_LITERALS
        )


_REGEX_RENDERER = _RegexRenderer()


@ensure(lambda result: not result.endswith("\\"))
def _render_comment_re_node(re_node: parse_retree.Node) -> Stripped:
    """Render the pattern as a comment without trailing spaces and line continuation."""
    parts = _REGEX_RENDERER.transform(re_node)
    assert all(
        isinstance(part, str) for part in parts
    ), f"Expected all rendered parts to be strings, but got: {parts}"

    text = "".join(parts)  # type: ignore

    if text.endswith((" ", "\t", "\n")):
        return Stripped(f"/* {text} */")

    if not text.endswith("\\"):
        return Stripped(f"// {text}")

    if "*/" not in text:
        return Stripped(f"/* {text} */")

    return Stripped(
        f"// {text}<PLACEHOLDER TO BREAK LINE CONTINUATION IN C++ COMMENTS>"
    )


@require(lambda indention: indention >= 0)
def _write_instructions_recursively(
    node_or_leaf: intermediate_revm.NodeOrLeaf, indention: int, writer: TextIO
) -> None:
    """Write recursively the creation of the program to the ``writer``."""
    whitespace = I * indention

    if isinstance(node_or_leaf, intermediate_revm.Leaf):
        maybe_label_comment = (
            "" if node_or_leaf.label is None else f"  // {node_or_leaf.label}"
        )

        instruction_code: Stripped

        if isinstance(node_or_leaf.instruction, intermediate_revm.InstructionChar):
            char_literal = cpp_common.wchar_literal(node_or_leaf.instruction.character)
            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::InstructionChar>({char_literal})
);"""
            )

        elif isinstance(
            node_or_leaf.instruction,
            (intermediate_revm.InstructionSet, intermediate_revm.InstructionNotSet),
        ):
            ranges: List[Stripped] = []
            for rng in node_or_leaf.instruction.ranges:
                first_literal = cpp_common.wchar_literal(rng.first)
                last_literal = cpp_common.wchar_literal(rng.last)
                ranges.append(Stripped(f"revm::Range({first_literal}, {last_literal})"))

            ranges_joined = ",\n".join(ranges)

            instruction_cls: Stripped
            if isinstance(node_or_leaf.instruction, intermediate_revm.InstructionSet):
                instruction_cls = Stripped("InstructionSet")
            elif isinstance(
                node_or_leaf.instruction, intermediate_revm.InstructionNotSet
            ):
                instruction_cls = Stripped("InstructionNotSet")
            else:
                # noinspection PyTypeChecker
                assert_never(node_or_leaf.instruction)

            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::{instruction_cls}>(
{II}std::vector<revm::Range>{{
{III}{indent_but_first_line(ranges_joined, III)}
{II}}}
{I})
);"""
            )

        elif isinstance(node_or_leaf.instruction, intermediate_revm.InstructionAny):
            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::InstructionAny>()
);"""
            )

        elif isinstance(node_or_leaf.instruction, intermediate_revm.InstructionMatch):
            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::InstructionMatch>()
);"""
            )

        elif isinstance(node_or_leaf.instruction, intermediate_revm.InstructionJump):
            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::InstructionJump>({node_or_leaf.instruction.target})
);"""
            )

        elif isinstance(node_or_leaf.instruction, intermediate_revm.InstructionSplit):
            first_target = node_or_leaf.instruction.first_target
            second_target = node_or_leaf.instruction.second_target
            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::InstructionSplit>({first_target}, {second_target})
);"""
            )

        elif isinstance(node_or_leaf.instruction, intermediate_revm.InstructionEnd):
            instruction_code = Stripped(
                f"""\
program.emplace_back({maybe_label_comment}
{I}common::make_unique<revm::InstructionEnd>()
);"""
            )

        else:
            # noinspection PyTypeChecker
            assert_never(node_or_leaf.instruction)

        writer.write(
            f"{whitespace}{indent_but_first_line(instruction_code, whitespace)}"
        )

    elif isinstance(node_or_leaf, intermediate_revm.Node):
        re_node_comment = _render_comment_re_node(node_or_leaf.re_node)

        if len(node_or_leaf.children) == 0:
            writer.write(
                f"{whitespace}{{  {re_node_comment}\n"
                f"{whitespace}{I}// Intentionally empty\n"
                f"{whitespace}}}"
            )
        elif len(node_or_leaf.children) == 1 and isinstance(
            node_or_leaf.children[0], intermediate_revm.Leaf
        ):
            writer.write(f"{whitespace}{re_node_comment}\n")
            _write_instructions_recursively(
                node_or_leaf=node_or_leaf.children[0],
                indention=indention,
                writer=writer,
            )
        else:
            writer.write(f"{whitespace}{{  {re_node_comment}\n")

            for child in node_or_leaf.children:
                _write_instructions_recursively(
                    node_or_leaf=child, indention=indention + 1, writer=writer
                )
                writer.write("\n")

            writer.write(f"{whitespace}}}  {re_node_comment}")
    else:
        # noinspection PyTypeChecker
        assert_never(node_or_leaf)


def _transpile_to_instructions(regex: parse_retree.Regex) -> Stripped:
    """
    Transpile the regular expression to instructions of the virtual machine.

    Please see :py:mod:`aas_core_codegen.cpp.revm` for details about the virtual machine
    for matching regular expressions.
    """
    root = intermediate_revm.translate(regex)

    writer = io.StringIO()
    _write_instructions_recursively(node_or_leaf=root, indention=0, writer=writer)

    return Stripped(writer.getvalue())


def _generate_program_definition_for_regex(regex: parse_retree.Regex) -> Stripped:
    """
    Generate the REVM program for the given parsed regular expression.

    We split this function from :py:func:`_generate_construct_function` so that we
    can manually invoke it or debug it on simpler examples.

    The returned block starts with the initialization of ``program`` variable.
    """
    # region Generate everything for the case that wide strings store UTF-32

    instructions_utf32 = _transpile_to_instructions(regex=regex)

    # endregion

    # region Generate everything for the case that wide strings store UTF-16

    parse_retree.fix_for_utf16_regex_in_place(regex=regex)

    instructions_utf16 = _transpile_to_instructions(regex=regex)

    # endregion

    body = [
        Stripped(
            """\
std::vector<std::unique_ptr<revm::Instruction> > program;"""
        )
    ]

    if instructions_utf32 == instructions_utf16:
        body.append(instructions_utf32)
    else:
        body.append(
            Stripped(
                f"""\
#if __WCHAR_MAX__ <= 0x10000
{I}// The size of wchar is 2 bytes.

{I}{indent_but_first_line(instructions_utf16, I)}
#else
{I}// The size of wchar is above 2 bytes.

{I}{indent_but_first_line(instructions_utf32, I)}
#endif"""
            )
        )

    return Stripped("\n\n".join(body))


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_construct_function(
    verification: intermediate.PatternVerification,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the constructor function for the program matching the given pattern."""
    regex, error = parse_retree.parse([verification.pattern])
    if error is not None:
        regex_line, pointer_line = parse_retree.render_pointer(error.cursor)

        return None, Error(
            verification.parsed.node,
            f"Failed to parse the pattern from "
            f"the pattern verification function {verification.name!r}:\n"
            f"{error.message}\n"
            f"{regex_line}\n"
            f"{pointer_line}",
        )

    assert regex is not None

    body = [
        _generate_program_definition_for_regex(regex=regex),
        Stripped("return program;"),
    ]

    body_joined = "\n\n".join(body)

    construct_function = cpp_naming.function_name(
        Identifier(f"construct_{verification.name}_program")
    )

    return (
        Stripped(
            f"""\
std::vector<
{I}std::unique_ptr<revm::Instruction>
> {construct_function}() {{
{I}{indent_but_first_line(body_joined, I)}
}}"""
        ),
        None,
    )


# fmt: off
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate implementation to specify regular expressions."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.PATTERN_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f'''\
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/pattern.hpp"
#include "{include_prefix_path}/revm.hpp"'''
        ),
        cpp_common.generate_namespace_opening(namespace),
    ]

    errors: List[Error] = []

    for verification in symbol_table.verification_functions:
        if not isinstance(verification, intermediate.PatternVerification):
            continue

        block, error = _generate_construct_function(verification=verification)
        if error is not None:
            errors.append(error)
            continue
        else:
            assert block is not None
            blocks.append(block)

        program_name = cpp_naming.constant_name(
            Identifier(f"{verification.name}_program")
        )

        construct_function = cpp_naming.function_name(
            Identifier(f"construct_{verification.name}_program")
        )

        blocks.append(
            Stripped(
                f"""\
const std::vector<
{I}std::unique_ptr<revm::Instruction>
> {program_name} = {construct_function}();"""
            )
        )

    if len(errors) > 0:
        return None, errors

    blocks.extend(
        [
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
