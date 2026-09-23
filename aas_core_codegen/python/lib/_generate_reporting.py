"""Generate the vocabulary for reporting the errors in the data."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


def _generate_module_docstring(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the docstring of the module."""
    return Stripped(
        f'''\
"""
Report where in the data an error lies.

A path is a sequence of segments which lead from the instance you handed over
down to the erroneous value. It renders as a Python access expression, so that
you can paste it as it stands:

.. code-block::

    .things[1].labels[0]

The vocabulary lives on its own so that
:py:mod:`{qualified_module_name}.verification`, and the verification of
a JSON-able value where the meta-model has one, report with the very same
classes.
"""'''
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(qualified_module_name: python_common.QualifiedModuleName) -> str:
    """
    Generate the code of the reporting vocabulary.

    The ``qualified_module_name`` indicates the fully-qualified name of the base
    module.
    """
    blocks = [
        _generate_module_docstring(qualified_module_name=qualified_module_name),
        python_common.WARNING,
        Stripped(
            f"""\
import collections
import sys
from typing import (
{I}Any,
{I}Deque,
{I}Mapping,
{I}Sequence,
{I}Union
)

if sys.version_info >= (3, 8):
{I}from typing import Final
else:
{I}from typing_extensions import Final

import {qualified_module_name}.types as aas_types"""
        ),
        python_common.generate_note_on_the_three_error_paths(
            qualified_module_name=qualified_module_name
        ),
        Stripped(
            f"""\
class PropertySegment:
{I}\"\"\"Represent a property access on a path to an erroneous value.\"\"\"

{I}#: Instance containing the property
{I}instance: Final[aas_types.Class]

{I}#: Name of the property
{I}name: Final[str]

{I}def __init__(
{III}self,
{III}instance: aas_types.Class,
{III}name: str
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.instance = instance
{II}self.name = name

{I}def __str__(self) -> str:
{II}return f'.{{self.name}}'"""
        ),
        Stripped(
            f"""\
class IndexSegment:
{I}\"\"\"Represent an index access on a path to an erroneous value.\"\"\"

{I}#: Sequence containing the item at :py:attr:`~index`
{I}sequence: Final[Sequence[Any]]

{I}#: Index of the item
{I}index: Final[int]

{I}def __init__(
{III}self,
{III}sequence: Sequence[Any],
{III}index: int
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.sequence = sequence
{II}self.index = index

{I}def __str__(self) -> str:
{II}return f'[{{self.index}}]'"""
        ),
        Stripped(
            f"""\
class KeySegment:
{I}\"\"\"
{I}Represent a member access on a path to an erroneous value.

{I}Unlike a :py:class:`PropertySegment`, which names a property of one of our
{I}classes, a key names a member of an open JSON-able object. It is known only
{I}at run time, and can be any string at all, so it is always rendered
{I}as a subscript.
{I}\"\"\"

{I}#: Mapping containing the value at :py:attr:`~key`
{I}mapping: Final[Mapping[str, Any]]

{I}#: Key of the value
{I}key: Final[str]

{I}def __init__(
{III}self,
{III}mapping: Mapping[str, Any],
{III}key: str
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.mapping = mapping
{II}self.key = key

{I}def __str__(self) -> str:
{II}return f'[{{self.key!r}}]'"""
        ),
        Stripped("Segment = Union[PropertySegment, IndexSegment, KeySegment]"),
        Stripped(
            f"""\
class Path:
{I}\"\"\"Represent the relative path to the erroneous value.\"\"\"

{I}def __init__(self) -> None:
{II}\"\"\"Initialize as an empty path.\"\"\"
{II}# NOTE (mristin):
{II}# A path is built as the stack unwinds, so every segment is prepended and
{II}# none is ever appended. A list would copy the whole path on each of them,
{II}# which makes a path of depth *d* cost *d^2* to build, while a deque
{II}# prepends in constant time.
{II}self._segments = collections.deque()  # type: Deque[Segment]

{I}@property
{I}def segments(self) -> Sequence[Segment]:
{II}\"\"\"Get the segments of the path.\"\"\"
{II}return self._segments

{I}def _prepend(self, segment: Segment) -> None:
{II}\"\"\"Insert the :paramref:`segment` in front of other segments.\"\"\"
{II}self._segments.appendleft(segment)

{I}def __str__(self) -> str:
{II}return "".join(str(segment) for segment in self._segments)"""
        ),
        Stripped(
            f"""\
class Error:
{I}\"\"\"Represent a verification error in the data.\"\"\"

{I}#: Human-readable description of the error
{I}cause: Final[str]

{I}#: Path to the erroneous value
{I}path: Final[Path]

{I}def __init__(self, cause: str) -> None:
{II}\"\"\"Initialize as an error with an empty path.\"\"\"
{II}self.cause = cause
{II}self.path = Path()

{I}def __repr__(self) -> str:
{II}return f"Error(path={{self.path}}, cause={{self.cause}})\""""
        ),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
