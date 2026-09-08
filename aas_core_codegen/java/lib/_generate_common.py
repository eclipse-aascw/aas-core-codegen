"""Generate code shared across the generated Java packages."""

from typing import List

from aas_core_codegen.common import Stripped
from aas_core_codegen.java import common as java_common


def _generate_tuple_record(arity: int) -> Stripped:
    """Generate the generic record representing a tuple of the given ``arity``."""
    type_params = ", ".join(f"T{i + 1}" for i in range(arity))
    components = ", ".join(f"T{i + 1} item{i + 1}" for i in range(arity))

    name = f"Tuple{arity}"

    return Stripped(
        f"""\
/**
 * Represent a fixed-size heterogeneous tuple of {arity} item(s).
 */
public record {name}<{type_params}>({components}) {{
}}"""
    )


def generate(
    package: java_common.PackageIdentifier,
) -> List[java_common.JavaFile]:
    """
    Generate code shared across the generated Java packages.

    This is generated unconditionally, regardless of whether the meta-model
    actually uses tuples, since the ``Tuple1`` .. ``Tuple8`` records are
    generic infrastructure, and not meta-model-derived types.
    """
    files = []  # type: List[java_common.JavaFile]

    for arity in range(1, java_common.MAX_TUPLE_ARITY + 1):
        record_code = _generate_tuple_record(arity=arity)

        blocks = [
            java_common.WARNING,
            Stripped(f"package {package}.common;"),
            record_code,
            java_common.WARNING,
        ]  # type: List[Stripped]

        code = "\n\n".join(blocks)

        files.append(java_common.JavaFile(f"Tuple{arity}.java", f"{code}\n"))

    return files


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
