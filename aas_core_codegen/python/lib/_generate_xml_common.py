"""Generate the XML primitives shared by the de/serialization modules."""

import io
from typing import List

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Stripped
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_module_docstring(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the docstring of the module."""
    return Stripped(
        f'''\
"""
Provide the primitives which the modules reading and writing XML share.

Reading means walking a stream of ``(event, element)`` tuples: checking that
an element resides in the expected namespace, consuming the end element which
corresponds to a start element and taking the text out of an element. Writing
means framing an element. Each of these is defined here exactly once, so that
neither :py:mod:`{qualified_module_name}.xmlization` nor the XML-RPC subset
over which a JSON-able value is de/serialized carries a copy of its own.

The namespace is a constant of this module, :py:attr:`NAMESPACE`, and no
argument of its primitives. This module is generated for a single meta-model,
and a meta-model prescribes exactly one namespace, so there is nothing for
a caller to choose.
"""'''
    )


def _generate_protocols() -> Stripped:
    """Generate the structural types of the element and of the parsing module."""
    return Stripped(
        f"""\
class Element(Protocol):
{I}\"\"\"Behave like :py:meth:`xml.etree.ElementTree.Element`.\"\"\"

{I}@property
{I}def attrib(self) -> Optional[Mapping[str, str]]:
{II}\"\"\"Attributes of the element\"\"\"
{II}raise NotImplementedError()

{I}@property
{I}def text(self) -> Optional[str]:
{II}\"\"\"Text content of the element\"\"\"
{II}raise NotImplementedError()

{I}@property
{I}def tail(self) -> Optional[str]:
{II}\"\"\"Tail text of the element\"\"\"
{II}raise NotImplementedError()

{I}@property
{I}def tag(self) -> str:
{II}\"\"\"Tag of the element; with a namespace provided as a ``{{...}}`` prefix\"\"\"
{II}raise NotImplementedError()

{I}def clear(self) -> None:
{II}\"\"\"Behave like :py:meth:`xml.etree.ElementTree.Element.clear`.\"\"\"
{II}raise NotImplementedError()"""
    )


# fmt: off
@require(
    lambda symbol_table:
    '"' not in symbol_table.meta_model.xml_namespace,
    "No double quotes expected in the XML namespace so that we can write it "
    "as-is in the ``xmlns`` attribute"
)
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> str:
    """
    Generate the code of the primitives shared by the XML de/serialization.

    The ``qualified_module_name`` indicates the fully-qualified name of the base
    module.
    """
    xml_namespace_literal = python_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    # NOTE (mristin):
    # The XML-RPC subset, over which the JSON-able values are de/serialized,
    # writes its elements in no namespace at all, as the XML-RPC specification
    # prescribes. The primitives which deal with such elements are therefore
    # only generated for a meta-model which actually has a JSON-able type.
    uses_json_types = intermediate.uses_json_types(symbol_table)

    parse_unqualified_element_tag_block = Stripped(
        f"""\
def parse_unqualified_element_tag(
{II}element: Element
) -> str:
{I}\"\"\"
{I}Extract the tag name of :paramref:`element`, which is expected to reside in
{I}no namespace at all.

{I}:param element: whose tag we want to extract
{I}:return: tag name
{I}:raise: :py:class:`DeserializationException` if unexpected :paramref:`element`
{I}\"\"\"
{I}if not element.tag.startswith('{{'):
{II}return element.tag

{I}got_namespace, _, tag_wo_ns = (
{II}element.tag[1:].partition('}}')
{I})

{I}raise DeserializationException(
{II}f"Expected the element in no namespace, "
{II}f"but got the element {{tag_wo_ns!r}} in "
{II}f"the namespace {{got_namespace!r}}"
{I})"""
    )

    open_in_no_namespace_field = (
        f"""
{I}#: Number of the currently open elements which reside in no namespace
{I}_open_in_no_namespace: int
"""
        if uses_json_types
        else ""
    )

    open_in_no_namespace_init = (
        f"""
{II}self._open_in_no_namespace = 0"""
        if uses_json_types
        else ""
    )

    in_no_namespace_methods = (
        f"""
{I}def write_start_element_in_no_namespace(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the start element with the tag name :paramref:`name`, which resides
{II}in no namespace at all.

{II}The outermost such element undeclares the default namespace, so that
{II}the elements nested in it reside in no namespace as well and need no
{II}declaration of their own.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}if self._open_in_no_namespace == 0:
{III}self.stream.write(f'<{{name}} xmlns="">')
{II}else:
{III}self.stream.write(f'<{{name}}>')

{II}self._open_in_no_namespace += 1

{I}def write_end_element_in_no_namespace(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the end element with the tag name :paramref:`name`, which resides in
{II}no namespace at all.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}self._open_in_no_namespace -= 1
{II}self.stream.write(f'</{{name}}>')
"""
        if uses_json_types
        else ""
    )

    blocks = [
        _generate_module_docstring(qualified_module_name=qualified_module_name),
        python_common.WARNING,
        # pylint: disable=line-too-long
        Stripped(
            f"""\
import re
import sys
from typing import (
{I}Callable,
{I}Iterator,
{I}List,
{I}Mapping,
{I}Optional,
{I}Sequence,
{I}TextIO,
{I}Tuple,
{I}Union
)

if sys.version_info >= (3, 8):
{I}from typing import (
{II}Final,
{II}Protocol
{I})
else:
{I}from typing_extensions import (
{II}Final,
{II}Protocol
{I})"""
        ),
        Stripped(
            f"""\
#: XML namespace in which all the elements of a document are expected to reside
NAMESPACE = {xml_namespace_literal}"""
        ),
        _generate_protocols(),
        # pylint: disable=line-too-long
        Stripped(
            f"""\
class HasIterparse(Protocol):
{I}\"\"\"Parse an XML document incrementally.\"\"\"

{I}# NOTE (mristin):
{I}# ``self`` is not used in this context, but is necessary for Mypy,
{I}# see: https://github.com/python/mypy/issues/5018 and
{I}# https://github.com/python/mypy/commit/3efbc5c5e910296a60ed5b9e0e7eb11dd912c3ed#diff-e165eb7aed9dca0a5ebd93985c8cd263a6462d36ac185f9461348dc5a1396d76R9937

{I}def iterparse(
{III}self,
{III}source: TextIO,
{III}events: Optional[Sequence[str]] = None
{I}) -> Iterator[Tuple[str, Element]]:
{II}\"\"\"Behave like :py:func:`xml.etree.ElementTree.iterparse`.\"\"\""""
        ),
        python_common.generate_note_on_the_three_error_paths(
            qualified_module_name=qualified_module_name
        ),
        Stripped(
            f"""\
class ElementSegment:
{I}\"\"\"Represent an element on a path to the erroneous value.\"\"\"
{I}#: Erroneous element
{I}element: Final[Element]

{I}def __init__(
{III}self,
{III}element: Element
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.element = element

{I}def __str__(self) -> str:
{II}\"\"\"
{II}Render the segment as a tag without the namespace.

{II}We deliberately omit the namespace in the tag names. If you want to actually
{II}query with the resulting XPath, you have to insert the namespaces manually.
{II}We did not know how to include the namespace in a meaningful way, as XPath
{II}assumes namespace prefixes to be defined *outside* of the document. At least
{II}the path thus rendered is informative, and you should be able to descend it
{II}manually.
{II}\"\"\"
{II}_, has_namespace, tag_wo_ns = self.element.tag.rpartition('}}')
{II}if not has_namespace:
{III}return self.element.tag
{II}else:
{III}return tag_wo_ns"""
        ),
        Stripped(
            f"""\
class IndexSegment:
{I}\"\"\"Represent an element in a sequence on a path to the erroneous value.\"\"\"
{I}#: Erroneous element
{I}element: Final[Element]

{I}#: Index of the element in the sequence
{I}index: Final[int]

{I}def __init__(
{III}self,
{III}element: Element,
{III}index: int
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.element = element
{II}self.index = index

{I}def __str__(self) -> str:
{II}\"\"\"Render the segment as an element wildcard with the index.\"\"\"
{II}return f'*[{{self.index}}]'"""
        ),
        Stripped(
            f"""\
class KeySegment:
{I}\"\"\"
{I}Represent a member of an open JSON-able object on a path to
{I}the erroneous element.

{I}Unlike an :py:class:`ElementSegment`, which names an element prescribed by
{I}the meta-model, a key is known only at run time, and can be any string
{I}at all.
{I}\"\"\"
{I}#: Element of the ``<member>`` which carries the key
{I}element: Final[Element]

{I}#: Key of the member
{I}key: Final[str]

{I}def __init__(
{III}self,
{III}element: Element,
{III}key: str
{I}) -> None:
{II}\"\"\"Initialize with the given values.\"\"\"
{II}self.element = element
{II}self.key = key

{I}def __str__(self) -> str:
{II}\"\"\"
{II}Render the segment as a predicate on the ``<name>`` child element.

{II}A JSON-able object is written as an XML-RPC ``<struct>``, which carries
{II}the key of a member in a ``<name>`` child element instead of in
{II}an attribute, so the XPath has to match on that child element.
{II}\"\"\"
{II}escaped = (
{III}self.key
{III}.replace('&', '&amp;')
{III}.replace('/', '&#47;')
{III}.replace('<', '&lt;')
{III}.replace('>', '&gt;')
{III}.replace('"', '&quot;')
{III}.replace("'", '&apos;')
{II})
{II}return f'member[name="{{escaped}}"]'"""
        ),
        Stripped(
            """\
Segment = Union[ElementSegment, IndexSegment, KeySegment]"""
        ),
        Stripped(
            f"""\
class Path:
{I}\"\"\"Represent the relative path to the erroneous element.\"\"\"

{I}def __init__(self) -> None:
{II}\"\"\"Initialize as an empty path.\"\"\"
{II}self._segments = []  # type: List[Segment]

{I}@property
{I}def segments(self) -> Sequence[Segment]:
{II}\"\"\"Get the segments of the path.\"\"\"
{II}return self._segments

{I}def _prepend(self, segment: Segment) -> None:
{II}\"\"\"Insert the :paramref:`segment` in front of other segments.\"\"\"
{II}self._segments.insert(0, segment)

{I}def __str__(self) -> str:
{II}\"\"\"Render the path as a relative XPath.

{II}We omit the leading ``/`` so that you can easily prefix it as you need.
{II}\"\"\"
{II}return "/".join(str(segment) for segment in self._segments)"""
        ),
        Stripped(
            f"""\
class DeserializationException(Exception):
{I}\"\"\"Signal that the XML de-serialization could not be performed.\"\"\"

{I}#: Human-readable explanation of the exception's cause
{I}cause: Final[str]

{I}#: Relative path to the erroneous value
{I}path: Final[Path]

{I}def __init__(
{III}self,
{III}cause: str
{I}) -> None:
{II}\"\"\"Initialize with the given :paramref:`cause` and an empty path.\"\"\"
{II}self.cause = cause
{II}self.path = Path()"""
        ),
        Stripped(
            f"""\
class SerializationException(Exception):
{I}\"\"\"Signal that the XML serialization could not be performed.\"\"\"

{I}#: Human-readable explanation of the exception's cause
{I}cause: Final[str]

{I}def __init__(
{III}self,
{III}cause: str
{I}) -> None:
{II}\"\"\"Initialize with the given :paramref:`cause` and an empty path.\"\"\"
{II}self.cause = cause
{II}self._segments = []  # type: List[str]

{I}@property
{I}def path(self) -> str:
{II}\"\"\"
{II}Render the path to the erroneous value as a Python access expression.

{II}The path points into the instance which you handed over for
{II}the serialization, and *not* into an XML document -- at the point of
{II}the failure, there is no document yet. For example, ``.submodels[0].id``
{II}tells you that the serialization broke on ``that.submodels[0].id``.

{II}Mind that the elements which the XML representation adds on top of
{II}the instance contribute no segment, as they correspond to no attribute
{II}access. This concerns the element enclosing the instance itself, and
{II}the element which designates the model type of the value of a property.
{II}\"\"\"
{II}return ''.join(self._segments)

{I}def _prepend_property(self, name: str) -> None:
{II}\"\"\"Insert the access to the property :paramref:`name` before the path.\"\"\"
{II}self._segments.insert(0, f'.{{name}}')

{I}def _prepend_index(self, index: int) -> None:
{II}\"\"\"Insert the access to the item at :paramref:`index` before the path.\"\"\"
{II}self._segments.insert(0, f'[{{index}}]')

{I}def _prepend_key(self, key: str) -> None:
{II}\"\"\"
{II}Insert the access to the member :paramref:`key` before the path.

{II}Unlike a property of one of our classes, a member of an open JSON-able
{II}object is known only at run time and can be any string at all, so it is
{II}always rendered as a subscript.
{II}\"\"\"
{II}self._segments.insert(0, f'[{{key!r}}]')

{I}def __str__(self) -> str:
{II}if len(self._segments) == 0:
{III}return self.cause

{II}return f'{{self.path}}: {{self.cause}}'"""
        ),
        Stripped("# region De-serialization"),
        Stripped(
            f"""\
def parse_element_tag(
{II}element: Element
) -> str:
{I}\"\"\"
{I}Extract the tag name without the namespace prefix from :paramref:`element`.

{I}:param element: whose tag without namespace we want to extract
{I}:return: tag name without the namespace prefix
{I}:raise: :py:class:`DeserializationException` if unexpected :paramref:`element`
{I}\"\"\"
{I}# NOTE (mristin):
{I}# :py:mod:`xml.etree.ElementTree` spells the tag of a namespaced element
{I}# as ``{{namespace}}tag``. We match that prefix in place, with
{I}# :py:meth:`str.startswith` and an offset, instead of composing
{I}# the ``{{...}}`` form: this runs for every element of every document, and
{I}# composing it would allocate a string on each call.
{I}if (
{II}element.tag.startswith('{{')
{II}and element.tag.startswith(NAMESPACE, 1)
{II}and element.tag.startswith('}}', len(NAMESPACE) + 1)
{I}):
{II}return element.tag[len(NAMESPACE) + 2:]

{I}got_namespace, separator, tag_wo_ns = (
{II}element.tag.rpartition('}}')
{I})

{I}if separator:
{II}if got_namespace.startswith('{{'):
{III}got_namespace = got_namespace[1:]

{II}raise DeserializationException(
{III}f"Expected the element in the namespace {{NAMESPACE!r}}, "
{III}f"but got the element {{tag_wo_ns!r}} in "
{III}f"the namespace {{got_namespace!r}}"
{II})

{I}raise DeserializationException(
{II}f"Expected the element in the namespace {{NAMESPACE!r}}, "
{II}f"but got the element {{tag_wo_ns!r}} without the namespace prefix"
{I})"""
        ),
        *([parse_unqualified_element_tag_block] if uses_json_types else []),
        Stripped(
            f'''\
def raise_if_non_whitespace_text(
{II}element: Element,
{II}expected_what: str
) -> None:
{I}"""
{I}Check that :paramref:`element` encloses no text of its own.

{I}An element which holds other elements may still be spelled over several
{I}lines, so the whitespace between its children is text as far as
{I}:py:mod:`xml.etree.ElementTree` is concerned. Anything else is not.

{I}:param element: to be verified
{I}:param expected_what: what the element was expected to enclose
{I}:raise:
{II}:py:class:`.DeserializationException` if there is text;
{II}conforming to the convention about handling error paths,
{II}the exception path is left empty.
{I}"""
{I}if element.text is not None and len(element.text.strip()) != 0:
{II}raise DeserializationException(
{III}f"Expected only {{expected_what}} and whitespace text, "
{III}f"but got text: {{element.text!r}}"
{II})'''
        ),
        Stripped(
            f'''\
def read_next_start_element(
{II}iterator: Iterator[Tuple[str, Element]],
{II}expected_what: str
) -> Element:
{I}"""
{I}Read the next start element from :paramref:`iterator`.

{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param expected_what: what we expected to read, for the error messages
{I}:raise:
{II}:py:class:`.DeserializationException` if the input ended, or if what came
{II}next was no start element; conforming to the convention about handling
{II}error paths, the exception path is left empty.
{I}:return: the start element
{I}"""
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}f"Expected the start element for {{expected_what}}, "
{III}f"but got the end-of-input"
{II})

{I}next_event, next_element = next_event_element
{I}if next_event != 'start':
{II}raise DeserializationException(
{III}f"Expected the start element for {{expected_what}}, "
{III}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{II})

{I}return next_element'''
        ),
        Stripped(
            f"""\
def raise_if_has_tail_or_attrib(
{II}element: Element
) -> None:
{I}\"\"\"
{I}Check that :paramref:`element` has no trailing text and no attributes.

{I}:param element: to be verified
{I}:raise:
{II}:py:class:`.DeserializationException` if trailing text or attributes;
{II}conforming to the convention about handling error paths,
{II}the exception path is left empty.
{I}\"\"\"
{I}if element.tail is not None and len(element.tail.strip()) != 0:
{II}raise DeserializationException(
{III}f"Expected no trailing text, but got: {{element.tail!r}}"
{II})

{I}if element.attrib is not None and len(element.attrib) > 0:
{II}raise DeserializationException(
{III}f"Expected no attributes, but got: {{element.attrib}}"
{II})"""
        ),
        Stripped(
            f"""\
def read_end_element(
{II}element: Element,
{II}iterator: Iterator[Tuple[str, Element]]
) -> Element:
{I}\"\"\"
{I}Read the end element corresponding to the start :paramref:`element`
{I}from :paramref:`iterator`.

{I}:param element: corresponding start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}\"\"\"
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}f"Expected the end element for {{element.tag}}, "
{III}f"but got the end-of-input"
{II})

{I}next_event, next_element = next_event_element
{I}if next_event != "end" or next_element.tag != element.tag:
{II}raise DeserializationException(
{III}f"Expected the end element for {{element.tag!r}}, "
{III}f"but got the event {{next_event!r}} and element {{next_element.tag!r}}"
{II})

{I}raise_if_has_tail_or_attrib(next_element)

{I}return next_element"""
        ),
        Stripped(
            f"""\
def read_text_from_element(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> str:
{I}\"\"\"
{I}Extract the text from the :paramref:`element`, and read
{I}the end element from :paramref:`iterator`.

{I}The :paramref:`element` is expected to contain text. Otherwise,
{I}it is considered as unexpected input.

{I}:param element: start element enclosing the text
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}\"\"\"
{I}raise_if_has_tail_or_attrib(element)

{I}text = element.text

{I}end_element = read_end_element(
{II}element,
{II}iterator,
{I})

{I}if text is None:
{II}if end_element.text is None:
{III}raise DeserializationException(
{IIII}"Expected an element with text, but got an element with no text."
{III})

{II}text = end_element.text

{I}return text"""
        ),
        Stripped(
            f'''\
def read_str_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> str:
{I}"""
{I}Parse the text of :paramref:`element` as a string, and
{I}read the corresponding end element from :paramref:`iterator`.

{I}If there is no text, empty string is returned.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}"""
{I}# NOTE (mristin):
{I}# We do not use ``read_text_from_element`` as that function expects
{I}# the ``element`` to contain *some* text. In contrast, this function
{I}# can also deal with empty text, in which case it returns an empty string.

{I}text = element.text

{I}end_element = read_end_element(
{II}element,
{II}iterator
{I})

{I}if text is None:
{II}text = end_element.text

{I}raise_if_has_tail_or_attrib(element)
{I}result = (
{II}text
{II}if text is not None
{II}else ""
{I})

{I}return result'''
        ),
        Stripped(
            """\
#: Match a run of the whitespace characters which XSD knows
XS_WHITESPACE_RE = re.compile(r"[ \\t\\n\\r]+")"""
        ),
        Stripped(
            f'''\
def collapse_whitespace(text: str) -> str:
{I}"""
{I}Normalize :paramref:`text` the way ``whiteSpace="collapse"`` prescribes.

{I}Every atomic XSD type except a string, and every type derived from one
{I}by restriction, fixes ``whiteSpace`` to ``collapse``, and a schema author
{I}can not change it. A tab, a line feed and a carriage return each become
{I}a space, a run of spaces becomes one space, and the leading and trailing
{I}spaces go. Only then is the result a lexical representation to be matched.

{I}Mind that this strips only the whitespace *around* the value: a space
{I}within it survives as a single space, so ``2  3`` becomes ``2 3``, which
{I}is still no number.

{I}See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace

{I}:param text: to be normalized
{I}:return: normalized text
{I}"""
{I}return XS_WHITESPACE_RE.sub(" ", text).strip(" ")'''
        ),
        Stripped("# endregion"),
        Stripped("# region Serialization"),
        Stripped(
            f"""\
class Writer:
{I}\"\"\"
{I}Write the XML elements of a single document to :py:attr:`~stream`.

{I}The namespace is specified on the very first element alone, and on none of
{I}the elements which follow it, so one writer serves exactly one document.
{I}\"\"\"

{I}#: Stream to be written to
{I}stream: Final[TextIO]
{open_in_no_namespace_field}
{I}#: Method pointer to be invoked for writing the start element with or without
{I}#: specifying a namespace (depending on the state of the writer)
{I}write_start_element: Callable[
{II}[str],
{II}None
{I}]

{I}#: Method pointer to be invoked for writing an empty element with or without
{I}#: specifying a namespace (depending on the state of the writer)
{I}write_empty_element: Callable[
{II}[str],
{II}None
{I}]

{I}# NOTE (mristin):
{I}# The serialization procedure is quite rigid. We leverage the specifics of
{I}# the serialization procedure to optimize the code a bit.
{I}#
{I}# Namely, we model the writing of the XML elements as a state machine.
{I}# The namespace is only specified for the very first element. All the subsequent
{I}# elements will *not* have the namespace specified. We implement that behavior by
{I}# using pointers to methods, as Python treats the methods as first-class citizens.
{I}#
{I}# The ``write_start_element`` will point to
{I}# ``_write_first_start_element_with_namespace`` on the *first* invocation.
{I}# Afterwards, it will be redirected to ``_write_start_element_without_namespace``.
{I}#
{I}# Analogously for ``write_empty_element``.
{I}#
{I}# Please see the implementation for the details, but this should give you at least
{I}# a rough overview.

{I}def _write_first_start_element_with_namespace(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the start element with the tag name :paramref:`name` and specify
{II}its namespace.

{II}The :py:attr:`~write_start_element` is set to
{II}:py:meth:`~_write_start_element_without_namespace` after the first invocation
{II}of this method.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}self.stream.write(f'<{{name}} xmlns="{{NAMESPACE}}">')

{II}# NOTE (mristin):
{II}# Any subsequence call to `write_start_element` or `write_empty_element`
{II}# should not specify the namespace of the element as we specified now already
{II}# specified it.
{II}self.write_start_element = self._write_start_element_without_namespace
{II}self.write_empty_element = self._write_empty_element_without_namespace

{I}def _write_start_element_without_namespace(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the start element with the tag name :paramref:`name`.

{II}The first element, written *before* this one, is expected to have been
{II}already written with the namespace specified.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}self.stream.write(f'<{{name}}>')

{I}def write_end_element(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the end element with the tag name :paramref:`name`.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}self.stream.write(f'</{{name}}>')
{in_no_namespace_methods}
{I}def _write_first_empty_element_with_namespace(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the first (and only) empty element with the tag name :paramref:`name`.

{II}No elements are expected to be written to the stream afterwards. The element
{II}includes the namespace specification.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}self.stream.write(f'<{{name}} xmlns="{{NAMESPACE}}"/>')
{II}self.write_empty_element = self._raise_if_write_element_called_again
{II}self.write_start_element = self._raise_if_write_element_called_again

{I}def _raise_if_write_element_called_again(
{III}self,
{III}name: str
{I}) -> None:
{II}raise AssertionError(
{III}f"We expected to call ``_write_first_empty_element_with_namespace`` "
{III}f"only once. This is an unexpected second call for writing "
{III}f"an (empty or non-empty) element with the tag name: {{name!r}}"
{II})

{I}def _write_empty_element_without_namespace(
{III}self,
{III}name: str
{I}) -> None:
{II}\"\"\"
{II}Write the empty element with the tag name :paramref:`name`.

{II}The call to this method is expected to occur *after* the enclosing element with
{II}a specified namespace has been written.

{II}:param name: of the element tag. Expected to contain no XML special characters.
{II}\"\"\"
{II}self.stream.write(f'<{{name}}/>')

{I}def __init__(
{II}self,
{II}stream: TextIO
{I}) -> None:
{II}\"\"\"
{II}Initialize the writer to write to :paramref:`stream`.

{II}The first element will include the :py:attr:`NAMESPACE`. Every other
{II}element will not have the namespace specified.

{II}:param stream: where to write to
{II}\"\"\"
{II}self.stream = stream{open_in_no_namespace_init}
{II}self.write_start_element = (
{III}self._write_first_start_element_with_namespace
{II})
{II}self.write_empty_element = (
{III}self._write_first_empty_element_with_namespace
{II})"""
        ),
        Stripped("# endregion"),
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
