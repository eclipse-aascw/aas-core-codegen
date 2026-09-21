"""Generate code of common functionality."""

import io

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
)
from aas_core_codegen.python import (
    common as python_common,
)
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
)


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code of common functionality."""
    blocks = [
        Stripped('"""Provide common functions shared among the modules."""'),
        python_common.WARNING,
        Stripped(
            f"""\
import collections.abc
from typing import (
{I}Any,
{I}NoReturn,
{I}Optional,
{I}Sequence
)"""
        ),
        Stripped(
            f"""\
def assert_never(value: NoReturn) -> NoReturn:
{I}\"\"\"
{I}Signal to mypy to perform an exhaustive matching.

{I}Please see the following page for more details:
{I}https://hakibenita.com/python-mypy-exhaustive-checking
{I}\"\"\"
{I}assert False, f"Unhandled value: {{value}} ({{type(value).__name__}})\""""
        ),
        Stripped(
            f'''\
def try_to_cast_to_array_like(
{I}value: Any
) -> Optional[Sequence[Any]]:
{I}"""
{I}Try to cast :paramref:`value` to something like a JSON array.

{I}A mapping and a set are refused, as neither is a JSON array, and so are
{I}a ``str``, a ``bytes`` and a ``bytearray``, which Python counts among
{I}the sequences but JSON does not.

{I}Only a sequence is admitted, and never an arbitrary iterable. A one-shot
{I}iterable such as a generator is spent by the first walk over it, so
{I}a verification followed by a serialization would silently give an empty
{I}array -- this function is the single place where all the modules agree on
{I}what an array is, so the refusal has to hold for all of them.

{I}>>> assert try_to_cast_to_array_like(True) is None

{I}>>> assert try_to_cast_to_array_like(0) is None

{I}>>> assert try_to_cast_to_array_like(2.2) is None

{I}>>> assert try_to_cast_to_array_like("hello") is None

{I}>>> assert try_to_cast_to_array_like(b"hello") is None

{I}>>> try_to_cast_to_array_like([1, 2])
{I}[1, 2]

{I}>>> assert try_to_cast_to_array_like({{"a": 3}}) is None

{I}>>> assert try_to_cast_to_array_like(collections.OrderedDict()) is None

{I}>>> try_to_cast_to_array_like(range(1, 2))
{I}range(1, 2)

{I}>>> try_to_cast_to_array_like((1, 2))
{I}(1, 2)

{I}>>> assert try_to_cast_to_array_like({{1, 2, 3}}) is None

{I}>>> assert try_to_cast_to_array_like(iter([1, 2])) is None
{I}"""
{I}# NOTE (mristin):
{I}# A ``list`` is what :py:mod:`json` gives us, and ``isinstance`` against
{I}# a concrete class costs a fraction of ``isinstance`` against the abstract
{I}# :py:class:`collections.abc.Sequence`, so we shortcut it here.
{I}if isinstance(value, list):
{II}return value

{I}if isinstance(value, (str, bytes, bytearray)):
{II}return None

{I}if isinstance(value, collections.abc.Sequence):
{II}return value

{I}return None'''
        ),
        python_common.WARNING,
    ]

    # NOTE (mristin):
    # Only a meta-model which uses a JSON-able type ever meets a bare number
    # whose type it does not already know, so the conversion is generated
    # only for such a model.
    if intermediate.uses_json_types(symbol_table):
        blocks.insert(
            len(blocks) - 1,
            Stripped(
                f'''\
def try_to_convert_int_to_float(
{I}value: int
) -> Optional[float]:
{I}"""
{I}Try to convert :paramref:`value` to the ``float`` which JSON prescribes.

{I}JSON knows a single numeric type, so an ``int`` has to become a ``float``
{I}on its way into and out of a JSON-able value. The conversion has to be
{I}exact: a ``float`` which does not convert back to :paramref:`value` would
{I}quietly say a different number than the one which was given, so such
{I}a value is refused instead of rounded.

{I}Mind that a ``bool`` is an ``int`` in Python. The callers all sort out
{I}the booleans before they come here.

{I}>>> try_to_convert_int_to_float(1)
{I}1.0

{I}>>> try_to_convert_int_to_float(-3)
{I}-3.0

{I}>>> assert try_to_convert_int_to_float(2 ** 53 + 1) is None

{I}>>> assert try_to_convert_int_to_float(10 ** 400) is None
{I}"""
{I}try:
{II}result = float(value)
{I}except OverflowError:
{II}# NOTE (mristin):
{II}# A Python ``int`` is unbounded, so one can be far too large for
{II}# a ``float`` to hold at all.
{II}return None

{I}if int(result) != value:
{II}return None

{I}return result'''
            ),
        )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
