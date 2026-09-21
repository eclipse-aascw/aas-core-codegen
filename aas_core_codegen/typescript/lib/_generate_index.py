"""Generate code of the index file which import all the other modules."""

import io
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate, specific_implementations
from aas_core_codegen.common import (
    Stripped,
    Error,
)
from aas_core_codegen.typescript import (
    common as typescript_common,
    description as typescript_description,
)


# fmt: off
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
    """Generate code of the index file which import all the other modules."""
    key = specific_implementations.ImplementationKey("package_documentation.txt")

    text = spec_impls.get(key, None)
    if text is None:
        return None, [
            Error(
                None,
                f"The package documentation snippet is missing "
                f"in the specific implementations: {key}",
            )
        ]

    text = Stripped(
        f"""\
{text}

@packageDocumentation"""
    )

    comment = Stripped(typescript_description.documentation_comment(text))

    # NOTE (mristin):
    # ``xmlrpc`` is only generated when the meta-model uses a JSON-able type, so
    # it is the only module which this index mentions conditionally.
    xml_rpc_export = (
        '\nexport * as xmlrpc from "./xmlrpc";'
        if intermediate.uses_json_types(symbol_table)
        else ""
    )

    blocks = [
        comment,
        typescript_common.WARNING,
        Stripped(
            f"""\
export * as common from "./common";
export * as constants from "./constants";
export * as jsonization from "./jsonization";
export * as xmlcommon from "./xmlcommon";
export * as xmlization from "./xmlization";{xml_rpc_export}
export * as stringification from "./stringification";
export * as types from "./types";
export * as verification from "./verification";"""
        ),
        typescript_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
