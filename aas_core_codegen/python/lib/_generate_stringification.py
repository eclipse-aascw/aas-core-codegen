"""Generate code for string de/serialization of enumerations."""

import io
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.common import Error, Stripped, Identifier
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import INDENT as I, INDENT2 as II


def _generate_enum_from_string(
    enumeration: intermediate.Enumeration,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the functions for de-serializing enumeration from strings."""
    blocks: List[Stripped] = []

    name = python_naming.enum_name(enumeration.name)

    # region From-string-map

    from_str_map_name = python_naming.constant_name(
        Identifier(f"_{enumeration.name}_from_str")
    )

    from_str_map_writer = io.StringIO()
    from_str_map_writer.write(
        f"""\
{from_str_map_name}: Mapping[str, our_types.{name}] = {{
"""
    )

    for literal in enumeration.literals:
        literal_name = python_naming.enum_literal_name(literal.name)
        from_str_map_writer.write(
            f"{I}{python_common.string_literal(literal.value)}: "
            f"our_types.{name}.{literal_name},\n"
        )

    from_str_map_writer.write("}")

    blocks.append(Stripped(from_str_map_writer.getvalue()))

    # endregion

    # region From-string-function

    from_str_name = python_naming.function_name(
        Identifier(f"{enumeration.name}_from_str")
    )

    from_str_writer = io.StringIO()
    from_str_writer.write(
        f"""\
def {from_str_name}(
{II}text: str
) -> Optional[our_types.{name}]:
{I}\"\"\"
{I}Parse :paramref:`text` as string representation
{I}of :py:class:`{qualified_module_name}.{name}`.

{I}If :paramref:`text` is not a valid string representation of a literal
{I}of :py:class:`{qualified_module_name}.{name}`, return ``None``.

{I}:param text: to be parsed
{I}:return:
{II}the corresponding literal of :py:class:`{qualified_module_name}.{name}`
{II}or ``None``, if :paramref:`text` invalid.
{I}\"\"\"
{I}return {from_str_map_name}.get(text)"""
    )

    blocks.append(Stripped(from_str_writer.getvalue()))

    # endregion

    return Stripped("\n\n\n".join(blocks))


def _generate_rank(
    enumeration: intermediate.Enumeration,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """
    Generate the ranking of the literals of the ``enumeration``.

    We rank the literals by their serialized values, compared by code points, at
    the time of the generation, so that all the SDKs sort the sets of
    the literals in the same order.
    """
    name = python_naming.enum_name(enumeration.name)

    rank_map_name = python_naming.constant_name(
        Identifier(f"_rank_of_{enumeration.name}")
    )

    rank_map_writer = io.StringIO()
    rank_map_writer.write(
        f"""\
{rank_map_name}: Final[Mapping[our_types.{name}, int]] = {{
"""
    )

    for rank, literal in enumerate(
        sorted(enumeration.literals, key=lambda a_literal: a_literal.value)
    ):
        literal_name = python_naming.enum_literal_name(literal.name)
        rank_map_writer.write(
            f"{I}our_types.{name}.{literal_name}: {rank},  "
            f"# {python_common.string_literal(literal.value)}\n"
        )

    rank_map_writer.write("}")

    rank_function_name = python_common.rank_function_name(enumeration)

    return Stripped(
        f"""\
{rank_map_writer.getvalue()}


def {rank_function_name}(
{II}literal: our_types.{name}
) -> int:
{I}\"\"\"
{I}Give out the rank of :paramref:`literal` in the serialization order.

{I}The sets of the literals of :py:class:`{qualified_module_name}.{name}` are
{I}serialized sorted by this rank, which follows the serialized values of
{I}the literals compared by their code points. The order is the same in all
{I}the SDKs generated from the meta-model.

{I}:param literal: to be ranked
{I}:return: position of :paramref:`literal` in the serialization order
{I}\"\"\"
{I}return {rank_map_name}[literal]"""
    )


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
    qualified_module_name: python_common.QualifiedModuleName,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for string de/serialization of enumerations.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    ranked_enumerations = intermediate_uses.enumerations_in_set_properties(symbol_table)

    # NOTE (mristin):
    # We import ``Final`` only for the ranks so that the import is never unused.
    imports = (
        Stripped(
            f"""\
import sys
from typing import (
{I}Mapping,
{I}Optional,
)

if sys.version_info >= (3, 8):
{I}from typing import Final
else:
{I}from typing_extensions import Final

import {qualified_module_name}.types as our_types"""
        )
        if len(ranked_enumerations) > 0
        else Stripped(
            f"""\
from typing import (
{I}Mapping,
{I}Optional,
)

import {qualified_module_name}.types as our_types"""
        )
    )

    blocks = [
        Stripped('"""De-serialize enumerations from string representations."""'),
        python_common.WARNING,
        imports,
    ]

    ranked_enumeration_ids = {id(enumeration) for enumeration in ranked_enumerations}

    for enum in symbol_table.enumerations:
        blocks.append(
            _generate_enum_from_string(
                enumeration=enum, qualified_module_name=qualified_module_name
            )
        )

        if id(enum) in ranked_enumeration_ids:
            blocks.append(
                _generate_rank(
                    enumeration=enum, qualified_module_name=qualified_module_name
                )
            )

    blocks.append(python_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
