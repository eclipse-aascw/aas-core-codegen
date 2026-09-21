"""Generate the de/serialization of the JSON-able values as an XML-RPC subset."""

import io
from typing import List

from icontract import ensure

from aas_core_codegen.common import Stripped
from aas_core_codegen.python import common as python_common
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_module_docstring(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the docstring of the module."""
    return Stripped(
        f'''\
"""
Read and write the JSON-able values as a subset of XML-RPC.

JSON prescribes no XML representation of its own, so we borrow the one of
XML-RPC for it: a value is written as a single discriminator element --
``<boolean>``, ``<double>``, ``<string>``, ``<array>`` or ``<struct>`` --
which says what the value is.

This module knows nothing of the meta-model beyond the JSON-able types, and
it drives no document of its own. The caller hands over the very stream of
``(event, element)`` tuples, or the very
:py:class:`{qualified_module_name}.xmlcommon.Writer`, with which
the enclosing document is being read or written, so that a JSON-able property
is read and written in the same pass as everything around it.

These elements reside in no namespace at all, as the XML-RPC specification
prescribes, and not in the namespace of the enclosing document. The outermost
one therefore undeclares the default namespace with ``xmlns=\"\"``, and
the elements nested in it inherit that.
"""'''
    )


def _generate_reading_blocks() -> List[Stripped]:
    """Generate the functions reading a JSON-able value."""
    return [
        Stripped(
            f'''\
def read_value_content(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.JsonValue:
{I}"""
{I}Read the content of :paramref:`element` as a JSON-able value.

{I}The content is a single discriminator element -- ``<boolean>``,
{I}``<double>``, ``<string>``, ``<array>`` or ``<struct>`` -- which says what
{I}the value is.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element enclosing the discriminator
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed JSON-able value
{I}"""
{I}raise_if_has_tail_or_attrib(element)
{I}raise_if_non_whitespace_text(element, 'a discriminator element')

{I}discriminator = read_next_start_element(
{II}iterator,
{II}'a discriminator '
{II}'(one of <boolean>, <double>, <string>, <array> or <struct>)'
{I})

{I}result = _read_discriminator(discriminator, iterator)

{I}read_end_element(element, iterator)

{I}return result'''
        ),
        Stripped(
            f'''\
#: Match a numeral of the ``<double>`` lexical space.
#:
#: This is the numeric part of the lexical space of ``xs:double``, and
#: deliberately not its three named literals -- ``INF``, ``-INF`` and ``NaN``
#: -- since a JSON number can be none of them.
#:
#: Mind the explicit ``[0-9]``: ``\\d`` would match a digit of any script, so
#: the Arabic-Indic ``۵`` would pass, and :py:func:`float` would read it
#: as 5.
#:
#: See: https://www.w3.org/TR/xmlschema-2/#double
_DOUBLE_RE = re.compile(
{I}r"(\\+|-)?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([Ee](\\+|-)?[0-9]+)?"
)


def _read_discriminator(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.JsonValue:
{I}"""
{I}Read :paramref:`element` as one of the five XML-RPC discriminators.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element of the discriminator
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed JSON-able value
{I}"""
{I}tag_wo_ns = parse_unqualified_element_tag(element)

{I}# NOTE (mristin):
{I}# The discriminator is an element which we actually enter, so it is a step
{I}# of the path. The one case which gets no step is the element which is no
{I}# discriminator at all, raised below and outside of this ``try``: it is that
{I}# very element which does not belong here, so naming it in the path as well
{I}# as in the message would say nothing more.
{I}try:
{II}if tag_wo_ns == 'boolean':
{III}# NOTE (mristin):
{III}# Real XML-RPC tooling writes and expects a strict ``1``/``0``, and not
{III}# the ``true``/``false`` which ``xs:boolean`` and the xmlization use.
{III}text = collapse_whitespace(read_text_from_element(element, iterator))
{III}if text == '1':
{IIII}return True
{III}if text == '0':
{IIII}return False

{III}raise DeserializationException(
{IIII}f"Expected \\"0\\" or \\"1\\" as the text of a <boolean> element, "
{IIII}f"but got: {{text!r}}"
{III})

{II}if tag_wo_ns == 'double':
{III}text = collapse_whitespace(read_text_from_element(element, iterator))

{III}# NOTE (mristin):
{III}# The lexical form is matched before the text is converted. ``float``
{III}# reads far more than we admit here: a hexadecimal significand, so
{III}# "0x10" would come out as 16, an underscore separator, and
{III}# the spellings "inf", "infinity" and "nan".
{III}#
{III}# Mind that the numeral excludes "INF", "-INF" and "NaN" on purpose,
{III}# unlike ``xs:double``, which names all three. A <double> carries
{III}# a JSON number, and JSON knows neither an infinity nor
{III}# a not-a-number, so there is no JSON-able value for such a text
{III}# to de-serialize into.
{III}if _DOUBLE_RE.fullmatch(text) is None:
{IIII}raise DeserializationException(
{IIIII}f"Expected a number as the text of a <double> element, "
{IIIII}f"but got: {{text!r}}"
{IIII})

{III}number = float(text)

{III}# NOTE (mristin):
{III}# A literal too large for a ``float`` gives an infinity, which is no
{III}# JSON-able value either, so it is refused rather than rounded.
{III}if not math.isfinite(number):
{IIII}raise DeserializationException(
{IIIII}f"Expected a number representable as a JSON-able value as "
{IIIII}f"the text of a <double> element, but got a value which "
{IIIII}f"rounds to an infinity: {{text!r}}"
{IIII})

{III}return number

{II}if tag_wo_ns == 'string':
{III}# NOTE (mristin):
{III}# ``xs:string`` is ``preserve`` and not ``collapse``, so a <string>
{III}# keeps its whitespace, unlike a <boolean> or a <double>.
{III}return read_str_from_element_text(element, iterator)

{II}if tag_wo_ns == 'array':
{III}return read_array_body(element, iterator)

{II}if tag_wo_ns == 'struct':
{III}return read_struct_body(element, iterator)
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(element))
{II}raise

{I}raise DeserializationException(
{II}f"Expected a discriminator element "
{II}f"(one of <boolean>, <double>, <string>, <array> or <struct>), "
{II}f"but got: {{tag_wo_ns!r}}"
{I})'''
        ),
        Stripped(
            f'''\
def read_array_body(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.JsonArray:
{I}"""
{I}Read the content of :paramref:`element` as a ``<data>`` of ``<value>``'s.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element enclosing the ``<data>``
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed JSON-able array
{I}"""
{I}raise_if_has_tail_or_attrib(element)

{I}raise_if_non_whitespace_text(element, 'a <data> element')

{I}data_element = read_next_start_element(iterator, 'a <data> element')
{I}if parse_unqualified_element_tag(data_element) != 'data':
{II}raise DeserializationException(
{III}f"Expected a start element <data>, "
{III}f"but got element {{data_element.tag!r}}"
{II})

{I}# NOTE (mristin):
{I}# The <data> element is a step of the path, as we enter it, and so is
{I}# the position of an item. The item's own <value> element is not: the index
{I}# already names it, so a step of its own would say nothing more.
{I}try:
{II}raise_if_non_whitespace_text(data_element, '<value> elements')

{II}result = []  # type: List[Any]

{II}while True:
{III}# NOTE (mristin):
{III}# We pull the next item element here instead of delegating it to
{III}# a helper, as this loop runs once for every item of every array.
{III}next_event_element = next(iterator, None)
{III}if next_event_element is None:
{IIII}raise DeserializationException(
{IIIII}f"Expected a <value> element or the end element corresponding "
{IIIII}f"to {{data_element.tag}}, but got the end-of-input"
{IIII})

{III}next_event, item_element = next_event_element
{III}if next_event == 'end' and item_element.tag == data_element.tag:
{IIII}# We reached the end element enclosing the items.
{IIII}break

{III}if next_event != 'start':
{IIII}raise DeserializationException(
{IIIII}f"Expected a start element corresponding to an item, "
{IIIII}f"but got event {{next_event!r}} "
{IIIII}f"and element {{item_element.tag!r}}"
{IIII})

{III}try:
{IIII}item = read_value_element(item_element, iterator)
{III}except DeserializationException as exception:
{IIII}exception.path._prepend(IndexSegment(item_element, len(result)))
{IIII}raise

{III}result.append(item)
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(data_element))
{II}raise

{I}read_end_element(element, iterator)

{I}return result'''
        ),
        Stripped(
            f'''\
def read_value_element(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.JsonValue:
{I}"""
{I}Read :paramref:`element`, which has to be a ``<value>``, as a JSON-able value.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element, expected to be a ``<value>``
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed JSON-able value
{I}"""
{I}tag_wo_ns = parse_unqualified_element_tag(element)
{I}if tag_wo_ns != 'value':
{II}raise DeserializationException(
{III}f"Expected a start element <value>, but got: {{tag_wo_ns!r}}"
{II})

{I}return read_value_content(element, iterator)'''
        ),
        Stripped(
            f'''\
def read_struct_body(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.JsonObject:
{I}"""
{I}Read the content of :paramref:`element` as a sequence of ``<member>``'s.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element enclosing the members
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed JSON-able object
{I}"""
{I}raise_if_has_tail_or_attrib(element)

{I}raise_if_non_whitespace_text(element, '<member> elements')

{I}result = dict()  # type: Dict[str, Any]

{I}while True:
{II}next_event_element = next(iterator, None)
{II}if next_event_element is None:
{III}raise DeserializationException(
{IIII}f"Expected a <member> element or the end element corresponding "
{IIII}f"to {{element.tag}}, but got the end-of-input"
{III})

{II}next_event, member_element = next_event_element
{II}if next_event == 'end' and member_element.tag == element.tag:
{III}break

{II}if (
{III}next_event != 'start'
{III}or parse_unqualified_element_tag(member_element) != 'member'
{II}):
{III}raise DeserializationException(
{IIII}f"Expected a start element <member>, but got "
{IIII}f"event {{next_event!r}} and element {{member_element.tag!r}}"
{III})

{II}key, value = _read_member(member_element, iterator)

{II}# NOTE (mristin):
{II}# A repeated <member> name is refused, just as a repeated property
{II}# element is refused in the xmlization. Letting the later member win
{II}# would silently accept a document which says two different things
{II}# about the same key.
{II}if key in result:
{III}exception = DeserializationException(
{IIII}"The member occurred more than once"
{III})
{III}exception.path._prepend(KeySegment(member_element, key))
{III}raise exception

{II}result[key] = value

{I}return result'''
        ),
        Stripped(
            f'''\
def _read_member(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> Tuple[str, aas_types.JsonValue]:
{I}"""
{I}Read :paramref:`element`, a ``<member>``, as a key and a JSON-able value.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element of the ``<member>``
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: the member's name and its parsed value
{I}"""
{I}raise_if_has_tail_or_attrib(element)

{I}raise_if_non_whitespace_text(
{II}element, 'a <name> and a <value> element'
{I})

{I}name_element = read_next_start_element(iterator, 'a <name> element')
{I}if parse_unqualified_element_tag(name_element) != 'name':
{II}raise DeserializationException(
{III}f"Expected a start element <name>, "
{III}f"but got element {{name_element.tag!r}}"
{II})

{I}key = read_str_from_element_text(name_element, iterator)

{I}# NOTE (mristin):
{I}# From here on the key is known, so every failure can name the member it
{I}# belongs to. A <struct> carries the key of a member in a <name> child
{I}# element instead of in an attribute, so the key segment renders as
{I}# a predicate on that child element, and the <member> element itself gets
{I}# no step of its own.
{I}try:
{II}value_element = read_next_start_element(
{III}iterator, 'a <value> element'
{II})

{II}try:
{III}value = read_value_element(value_element, iterator)
{II}except DeserializationException as exception:
{III}exception.path._prepend(ElementSegment(value_element))
{III}raise
{I}except DeserializationException as exception:
{II}exception.path._prepend(KeySegment(element, key))
{II}raise

{I}read_end_element(element, iterator)

{I}return key, value'''
        ),
    ]


def _generate_writing_blocks() -> List[Stripped]:
    """Generate the functions writing a JSON-able value."""
    return [
        Stripped(
            f'''\
def write_discriminator(
{I}value: aas_types.JsonValue,
{I}writer: Writer
) -> None:
{I}"""
{I}Write :paramref:`value` as one of the five XML-RPC discriminators.

{I}:param value: to be serialized
{I}:param writer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}"""
{I}# NOTE (mristin):
{I}# A ``bool`` is an ``int`` in Python, so it has to be checked first --
{I}# otherwise every boolean would be written as a number.
{I}if isinstance(value, bool):
{II}# NOTE (mristin):
{II}# Real XML-RPC tooling writes and expects a strict ``1``/``0``, and not
{II}# the ``true``/``false`` which ``xs:boolean`` and the xmlization use.
{II}writer.write_start_element_in_no_namespace('boolean')
{II}writer.stream.write('1' if value else '0')
{II}writer.write_end_element_in_no_namespace('boolean')
{II}return

{I}if isinstance(value, int):
{II}# NOTE (mristin):
{II}# An ``int`` is written out as it stands, free of the fraction which
{II}# a ``float`` carries. JSON knows a single numeric type, though, so
{II}# it has to be one which a ``float`` can hold exactly -- otherwise
{II}# a reader, which reads every <double> as a ``float``, would get
{II}# a different number back.
{II}if aas_common.try_to_convert_int_to_float(value) is None:
{III}raise SerializationException(
{IIII}f"Expected a JSON-able value, but got the integer {{value}}, "
{IIII}f"which is not exactly representable as a JSON number"
{III})

{II}writer.write_start_element_in_no_namespace('double')
{II}writer.stream.write(str(value))
{II}writer.write_end_element_in_no_namespace('double')
{II}return

{I}if isinstance(value, float):
{II}# NOTE (mristin):
{II}# JSON knows neither an infinity nor a not-a-number, so neither is
{II}# a JSON-able value, and ``_read_discriminator`` refuses to read
{II}# either back.
{II}if not math.isfinite(value):
{III}raise SerializationException(
{IIII}f"Expected a JSON-able value, but got the number {{value}}, "
{IIII}f"which is neither finite nor representable in JSON"
{III})

{II}writer.write_start_element_in_no_namespace('double')

{II}# NOTE (mristin):
{II}# ``str`` spells a negative zero as "-0.0", but only if the sign is
{II}# looked at: ``value == 0`` holds for both zeroes.
{II}if value == 0 and math.copysign(1.0, value) < 0.0:
{III}writer.stream.write('-0.0')
{II}else:
{III}writer.stream.write(str(value))

{II}writer.write_end_element_in_no_namespace('double')
{II}return

{I}if isinstance(value, str):
{II}writer.write_start_element_in_no_namespace('string')
{II}writer.stream.write(
{III}value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
{II})
{II}writer.write_end_element_in_no_namespace('string')
{II}return

{I}if isinstance(value, (dict, collections.abc.Mapping)):
{II}writer.write_start_element_in_no_namespace('struct')
{II}write_struct_body(value, writer)
{II}writer.write_end_element_in_no_namespace('struct')
{II}return

{I}array_like = aas_common.try_to_cast_to_array_like(value)
{I}if array_like is not None:
{II}writer.write_start_element_in_no_namespace('array')
{II}write_array_body(array_like, writer)
{II}writer.write_end_element_in_no_namespace('array')
{II}return

{I}raise SerializationException(
{II}f"Expected a JSON-able value (a boolean, a number, a string, an array "
{II}f"or an object), but got: {{type(value)}}"
{I})'''
        ),
        Stripped(
            f'''\
def write_array_body(
{I}value: aas_types.JsonArray,
{I}writer: Writer
) -> None:
{I}"""
{I}Write the ``<data>`` of the JSON-able array :paramref:`value`.

{I}The path of a failure points into :paramref:`value`, and not into
{I}the document, which is only half written when the failure is raised: it is
{I}the value which the caller holds and can look at.

{I}:param value: to be serialized
{I}:param writer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}"""
{I}writer.write_start_element_in_no_namespace('data')
{I}for i, item in enumerate(value):
{II}writer.write_start_element_in_no_namespace('value')
{II}try:
{III}write_discriminator(item, writer)
{II}except SerializationException as exception:
{III}exception._prepend_index(i)
{III}raise
{II}writer.write_end_element_in_no_namespace('value')
{I}writer.write_end_element_in_no_namespace('data')'''
        ),
        Stripped(
            f'''\
def write_struct_body(
{I}value: aas_types.JsonObject,
{I}writer: Writer
) -> None:
{I}"""
{I}Write the ``<member>``'s of the JSON-able object :paramref:`value`.

{I}The path of a failure points into :paramref:`value`, and not into
{I}the document, which is only half written when the failure is raised: it is
{I}the value which the caller holds and can look at.

{I}:param value: to be serialized
{I}:param writer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}"""
{I}for key, item in value.items():
{II}if not isinstance(key, str):
{III}# NOTE (mristin):
{III}# A key which is no string names nothing which the path could
{III}# descend into, so the path stops at the object which holds it.
{III}raise SerializationException(
{IIII}f"Expected only string keys in a JSON-able object, but got "
{IIII}f"a key of type: {{type(key)}}"
{III})

{II}writer.write_start_element_in_no_namespace('member')

{II}writer.write_start_element_in_no_namespace('name')
{II}writer.stream.write(
{III}key.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
{II})
{II}writer.write_end_element_in_no_namespace('name')

{II}writer.write_start_element_in_no_namespace('value')
{II}try:
{III}write_discriminator(item, writer)
{II}except SerializationException as exception:
{III}exception._prepend_key(key)
{III}raise
{II}writer.write_end_element_in_no_namespace('value')

{II}writer.write_end_element_in_no_namespace('member')'''
        ),
    ]


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(qualified_module_name: python_common.QualifiedModuleName) -> str:
    """
    Generate the code of the XML-RPC de/serialization of the JSON-able values.

    The ``qualified_module_name`` indicates the fully-qualified name of the base
    module.
    """
    blocks = [
        _generate_module_docstring(qualified_module_name=qualified_module_name),
        python_common.WARNING,
        Stripped(
            f"""\
import collections.abc
import math
import re
from typing import (
{I}Any,
{I}Dict,
{I}Iterator,
{I}List,
{I}Tuple
)

import {qualified_module_name}.common as aas_common
import {qualified_module_name}.types as aas_types
from {qualified_module_name}.xmlcommon import (
{I}DeserializationException,
{I}Element,
{I}ElementSegment,
{I}IndexSegment,
{I}KeySegment,
{I}SerializationException,
{I}Writer,
{I}collapse_whitespace,
{I}parse_unqualified_element_tag,
{I}raise_if_has_tail_or_attrib,
{I}raise_if_non_whitespace_text,
{I}read_end_element,
{I}read_next_start_element,
{I}read_str_from_element_text,
{I}read_text_from_element
)"""
        ),
        Stripped("# region De-serialization"),
    ]  # type: List[Stripped]

    blocks.extend(_generate_reading_blocks())

    blocks.append(Stripped("# endregion"))
    blocks.append(Stripped("# region Serialization"))

    blocks.extend(_generate_writing_blocks())

    blocks.append(Stripped("# endregion"))

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()
