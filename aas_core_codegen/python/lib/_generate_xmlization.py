"""Generate code for XML de/serialization."""

import io
import textwrap
from typing import Tuple, Optional, List, Union

from icontract import ensure, require

from aas_core_codegen import intermediate, specific_implementations, naming
from aas_core_codegen.common import (
    Error,
    Stripped,
    assert_never,
    Identifier,
    indent_but_first_line,
)
from aas_core_codegen.python import common as python_common, naming as python_naming
from aas_core_codegen.python.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_module_docstring(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the docstring of the whole module."""
    first_cls = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )

    docstring_blocks = [
        Stripped(
            f"""\
Read and write AAS models as XML.

For reading, we provide different reading functions, each handling a different kind
of input. All the reading functions operate in one pass, *i.e.*, the source is read
incrementally and the complete XML is not held in memory.

We provide the following four reading functions (where ``X`` represents the name of
the class):

1) ``X_from_iterparse`` reads from a stream of ``(event, element)`` tuples coming from
   :py:func:`xml.etree.ElementTree.iterparse` with the argument
   ``events=["start", "end"]``. If you do not trust the source, please consider
   using `defusedxml.ElementTree`_.
2) ``X_from_stream`` reads from the given text stream.
3) ``X_from_file`` reads from a file on disk.
4) ``X_from_str`` reads from the given string.

The functions ``X_from_stream``, ``X_from_file`` and ``X_from_str`` provide
an extra parameter, ``has_iterparse``, which allows you to use a parsing library
different from :py:mod:`xml.etree.ElementTree`. For example, you can pass in
`defusedxml.ElementTree`_.

.. _defusedxml.ElementTree: https://pypi.org/project/defusedxml/#defusedxml-elementtree

All XML elements are expected to live in the :py:attr:`~NAMESPACE`.

For writing, use the function :py:func:`{qualified_module_name}.xmlization.write` which
translates the instance of the model into an XML document and writes it in one pass
to the stream."""
        )
    ]

    if first_cls is not None:
        read_first_cls_from_file = python_naming.function_name(
            Identifier(f"read_{first_cls.name}_from_file")
        )

        first_cls_name = python_naming.class_name(first_cls.name)

        docstring_blocks.append(
            Stripped(
                f"""\
Here is an example usage how to de-serialize from a file:

.. code-block::

    import pathlib
    import xml.etree.ElementTree as ET

    import {qualified_module_name}.xmlization as aas_xmlization

    path = pathlib.Path(...)
    instance = aas_xmlization.{read_first_cls_from_file}(
        path
    )

    # Do something with the ``instance``

Here is another code example where we serialize the instance:

.. code-block::

    import pathlib

    import {qualified_module_name}.types as aas_types
    import {qualified_module_name}.xmlization as aas_xmlization

    instance = {first_cls_name}(
       ... # some constructor arguments
    )

    pth = pathlib.Path(...)
    with pth.open("wt") as fid:
        aas_xmlization.write(instance, fid)"""
            )
        )

    escaped_text = "\n\n".join(docstring_blocks).replace('"""', '\\"\\"\\"')
    return Stripped(
        f"""\
\"\"\"
{escaped_text}
\"\"\""""
    )


def _generate_read_enum_from_element_text(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    """Generate the reading function from an element's text for ``enumeration``."""
    enum_name = python_naming.enum_name(identifier=enumeration.name)

    function_name = python_naming.private_function_name(
        Identifier(f"read_{enumeration.name}_from_element_text")
    )

    enum_from_str = python_naming.function_name(
        Identifier(f"{enumeration.name}_from_str")
    )

    return Stripped(
        f"""\
def {function_name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.{enum_name}:
{I}\"\"\"
{I}Parse the text of :paramref:`element` as a literal of
{I}:py:class:`.types.{enum_name}`, and read the corresponding
{I}end element from :paramref:`iterator`.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}\"\"\"
{I}text = _read_text_from_element(
{II}element,
{II}iterator
{I})

{I}literal = aas_stringification.{enum_from_str}(text)
{I}if literal is None:
{II}raise DeserializationException(
{III}f"Not a valid string representation of "
{III}f"a literal of {enum_name}: {{text}}"
{II})

{I}return literal"""
    )


def _generate_read_cls_from_iterparse(
    cls: Union[intermediate.AbstractClass, intermediate.ConcreteClass],
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the public function for the reading for a ``cls``."""
    function_name = python_naming.function_name(
        Identifier(f"{cls.name}_from_iterparse")
    )

    cls_name = python_naming.class_name(cls.name)

    wrapped_function_name = python_naming.function_name(
        Identifier(f"_read_{cls.name}_as_element")
    )

    return Stripped(
        f"""\
def {function_name}(
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.{cls_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{cls_name}` from
{I}the :paramref:`iterator`.

{I}Example usage:

{I}.. code-block::

{I}    import pathlib
{I}    import xml.etree.ElementTree as ET

{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    path = pathlib.Path(...)
{I}    with path.open("rt") as fid:
{I}        iterator = ET.iterparse(
{I}            source=fid,
{I}            events=['start', 'end']
{I}        )
{I}        instance = aas_xmlization.{function_name}(
{I}            iterator
{I}        )

{I}    # Do something with the ``instance``

{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance of :py:class:`.types.{cls_name}` read from
{II}:paramref:`iterator`
{I}\"\"\"
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}# fmt: off
{III}"Expected the start element for {cls_name}, "
{III}"but got the end-of-input"
{III}# fmt: on
{II})

{I}next_event, next_element = next_event_element
{I}if next_event != 'start':
{II}raise DeserializationException(
{III}f"Expected the start element for {cls_name}, "
{III}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{II})

{I}try:
{II}return {wrapped_function_name}(
{III}next_element,
{III}iterator
{II})
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(next_element))
{II}raise exception"""
    )


def _generate_read_cls_from_stream(
    cls: Union[intermediate.AbstractClass, intermediate.ConcreteClass],
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the public function for the reading of a ``cls`` from a stream."""
    function_name = python_naming.function_name(Identifier(f"{cls.name}_from_stream"))

    from_iterparse_name = python_naming.function_name(
        Identifier(f"{cls.name}_from_iterparse")
    )

    cls_name = python_naming.class_name(cls.name)

    return Stripped(
        f"""\
def {function_name}(
{I}stream: TextIO,
{I}has_iterparse: HasIterparse = xml.etree.ElementTree
) -> aas_types.{cls_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{cls_name}` from
{I}the :paramref:`stream`.

{I}Example usage:

{I}.. code-block::

{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    with open_some_stream_over_network(...) as stream:
{I}        instance = aas_xmlization.{function_name}(
{I}            stream
{I}        )

{I}    # Do something with the ``instance``

{I}:param stream:
{II}representing an instance of
{II}:py:class:`.types.{cls_name}` in XML
{I}:param has_iterparse:
{II}Module containing ``iterparse`` function.

{II}Default is to use :py:mod:`xml.etree.ElementTree` from the standard
{II}library. If you have to deal with malicious input, consider using
{II}a library such as `defusedxml.ElementTree`_.
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance of :py:class:`.types.{cls_name}` read from
{II}:paramref:`stream`
{I}\"\"\"
{I}iterator = has_iterparse.iterparse(
{II}stream,
{II}['start', 'end']
{I})
{I}return {from_iterparse_name}(
{II}_with_elements_cleared_after_yield(iterator)
{I})"""
    )


def _generate_read_cls_from_file(
    cls: Union[intermediate.AbstractClass, intermediate.ConcreteClass],
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the public function for the reading of a ``cls`` from a file."""
    function_name = python_naming.function_name(Identifier(f"{cls.name}_from_file"))

    from_iterparse_name = python_naming.function_name(
        Identifier(f"{cls.name}_from_iterparse")
    )

    cls_name = python_naming.class_name(cls.name)

    return Stripped(
        f"""\
def {function_name}(
{I}path: PathLike,
{I}has_iterparse: HasIterparse = xml.etree.ElementTree
) -> aas_types.{cls_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{cls_name}` from
{I}the :paramref:`path`.

{I}Example usage:

{I}.. code-block::

{I}    import pathlib
{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    path = pathlib.Path(...)
{I}    instance = aas_xmlization.{function_name}(
{I}        path
{I}    )

{I}    # Do something with the ``instance``

{I}:param path:
{II}to the file representing an instance of
{II}:py:class:`.types.{cls_name}` in XML
{I}:param has_iterparse:
{II}Module containing ``iterparse`` function.

{II}Default is to use :py:mod:`xml.etree.ElementTree` from the standard
{II}library. If you have to deal with malicious input, consider using
{II}a library such as `defusedxml.ElementTree`_.
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance of :py:class:`.types.{cls_name}` read from
{II}:paramref:`path`
{I}\"\"\"
{I}with open(os.fspath(path), "rt", encoding='utf-8') as fid:
{II}iterator = has_iterparse.iterparse(
{III}fid,
{III}['start', 'end']
{II})
{II}return {from_iterparse_name}(
{III}_with_elements_cleared_after_yield(iterator)
{II})"""
    )


def _generate_read_cls_from_str(
    cls: Union[intermediate.AbstractClass, intermediate.ConcreteClass],
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the public function for the reading of a ``cls`` from a string."""
    function_name = python_naming.function_name(Identifier(f"{cls.name}_from_str"))

    from_iterparse_name = python_naming.function_name(
        Identifier(f"{cls.name}_from_iterparse")
    )

    cls_name = python_naming.class_name(cls.name)

    return Stripped(
        f"""\
def {function_name}(
{I}text: str,
{I}has_iterparse: HasIterparse = xml.etree.ElementTree
) -> aas_types.{cls_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{cls_name}` from
{I}the :paramref:`text`.

{I}Example usage:

{I}.. code-block::

{I}    import pathlib
{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    text = "<...>...</...>"
{I}    instance = aas_xmlization.{function_name}(
{I}        text
{I}    )

{I}    # Do something with the ``instance``

{I}:param text:
{II}representing an instance of
{II}:py:class:`.types.{cls_name}` in XML
{I}:param has_iterparse:
{II}Module containing ``iterparse`` function.

{II}Default is to use :py:mod:`xml.etree.ElementTree` from the standard
{II}library. If you have to deal with malicious input, consider using
{II}a library such as `defusedxml.ElementTree`_.
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance of :py:class:`.types.{cls_name}` read from
{II}:paramref:`text`
{I}\"\"\"
{I}iterator = has_iterparse.iterparse(
{II}io.StringIO(text),
{II}['start', 'end']
{I})
{I}return {from_iterparse_name}(
{II}_with_elements_cleared_after_yield(iterator)
{I})"""
    )


# fmt: off
@require(
    lambda cls:
    not isinstance(cls, intermediate.AbstractClass)
    or len(cls.concrete_descendants) > 0,
    "All abstract classes must have concrete descendants; otherwise we can not dispatch"
)
# fmt: on
def _generate_read_cls_as_element(
    cls: Union[intermediate.AbstractClass, intermediate.ConcreteClass]
) -> Stripped:
    """Generate the read function to dispatch or read a concrete instance of ``cls``."""

    if len(cls.concrete_descendants) > 0:
        dispatch_map = python_naming.private_constant_name(
            Identifier(f"dispatch_for_{cls.name}")
        )

        cls_name = python_naming.class_name(cls.name)

        body = Stripped(
            f"""\
tag_wo_ns = _parse_element_tag(element)
read_as_sequence = {dispatch_map}.get(
{I}tag_wo_ns,
{I}None
)

if read_as_sequence is None:
{I}raise DeserializationException(
{II}f"Expected the element tag to be a valid model type "
{II}f"of a concrete instance of '{cls_name}', "
{II}f"but got tag {{tag_wo_ns!r}}"
{I})

return read_as_sequence(
{I}element,
{I}iterator
)"""
        )
    else:
        xml_cls = naming.xml_class_name(cls.name)
        xml_cls_literal = python_common.string_literal(xml_cls)

        read_as_sequence_function_name = python_naming.function_name(
            Identifier(f"_read_{cls.name}_as_sequence")
        )

        body = Stripped(
            f"""\
tag_wo_ns = _parse_element_tag(element)

if tag_wo_ns != {xml_cls_literal}:
{I}raise DeserializationException(
{II}f"Expected the element with the tag '{xml_cls}', "
{II}f"but got tag: {{tag_wo_ns}}"
{I})

return {read_as_sequence_function_name}(
{I}element,
{I}iterator
)"""
        )

    function_name = python_naming.function_name(
        Identifier(f"_read_{cls.name}_as_element")
    )

    cls_name = python_naming.class_name(cls.name)

    return Stripped(
        f"""\
def {function_name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.{cls_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{cls_name}` from
{I}:paramref:`iterator`, including the end element.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_dispatch_map_for_named_union(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """Generate the mapping model type 🠒 read-as-sequence function."""
    mapping_name = python_naming.private_constant_name(
        Identifier(f"dispatch_for_{named_union.name}")
    )

    union_name = python_naming.union_name(named_union.name)

    mapping_writer = io.StringIO()

    mapping_writer.write(
        f"""\
#: Dispatch XML class names to read-as-sequence functions
#: corresponding to the implementers of {union_name}
{mapping_name}: Mapping[
{I}str,
{I}Callable[
{II}[
{III}Element,
{III}Iterator[Tuple[str, Element]]
{II}],
{II}aas_types.{union_name}
{I}]
] = {{
"""
    )

    for implementer in named_union.implementers:
        read_as_sequence_name = python_naming.private_function_name(
            Identifier(f"read_{implementer.name}_as_sequence")
        )

        xml_name_literal = python_common.string_literal(
            naming.xml_class_name(implementer.name)
        )

        mapping_writer.write(
            f"""\
{I}{xml_name_literal}: {read_as_sequence_name},
"""
        )

    mapping_writer.write("}")

    return Stripped(mapping_writer.getvalue())


def _generate_read_named_union_as_element(
    named_union: intermediate.NamedUnion,
) -> Stripped:
    """
    Generate the read function to dispatch to a concrete instance of the union.

    Unlike a plain, non-polymorphic class, a named union always dispatches on
    the element's own tag, regardless of how its members disambiguate on the
    JSON side, since an XML element is always self-tagging.
    """
    dispatch_map = python_naming.private_constant_name(
        Identifier(f"dispatch_for_{named_union.name}")
    )

    union_name = python_naming.union_name(named_union.name)

    body = Stripped(
        f"""\
tag_wo_ns = _parse_element_tag(element)
read_as_sequence = {dispatch_map}.get(
{I}tag_wo_ns,
{I}None
)

if read_as_sequence is None:
{I}raise DeserializationException(
{II}f"Expected the element tag to be a valid model type "
{II}f"of a concrete instance of '{union_name}', "
{II}f"but got tag {{tag_wo_ns!r}}"
{I})

return read_as_sequence(
{I}element,
{I}iterator
)"""
    )

    function_name = python_naming.function_name(
        Identifier(f"_read_{named_union.name}_as_element")
    )

    return Stripped(
        f"""\
def {function_name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.{union_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{union_name}` from
{I}:paramref:`iterator`, including the end element.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
    )


def _generate_read_from_iterparse(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the general read function to parse an instance from iterparse."""
    function_name = "from_iterparse"

    return Stripped(
        f"""\
def {function_name}(
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.Class:
{I}\"\"\"
{I}Read an instance from the :paramref:`iterator`.

{I}The type of the instance is determined by the very first start element.

{I}Example usage:

{I}.. code-block::

{I}    import pathlib
{I}    import xml.etree.ElementTree as ET

{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    path = pathlib.Path(...)
{I}    with path.open("rt") as fid:
{I}        iterator = ET.iterparse(
{I}            source=fid,
{I}            events=['start', 'end']
{I}        )
{I}        instance = aas_xmlization.{function_name}(
{I}            iterator
{I}        )

{I}    # Do something with the ``instance``

{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance of :py:class:`.types.Class` read from the :paramref:`iterator`
{I}\"\"\"
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}# fmt: off
{III}"Expected the start element of an instance, "
{III}"but got the end-of-input"
{III}# fmt: on
{II})

{I}next_event, next_element = next_event_element
{I}if next_event != 'start':
{II}raise DeserializationException(
{III}f"Expected the start element of an instance, "
{III}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{II})

{I}try:
{II}return _read_as_element(
{III}next_element,
{III}iterator
{II})
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(next_element))
{II}raise exception"""
    )


def _generate_read_from_stream(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the general read function to parse an instance from a text stream."""
    function_name = python_naming.function_name(Identifier("from_stream"))

    return Stripped(
        f"""\
def {function_name}(
{I}stream: TextIO,
{I}has_iterparse: HasIterparse = xml.etree.ElementTree
) -> aas_types.Class:
{I}\"\"\"
{I}Read an instance from the :paramref:`stream`.

{I}The type of the instance is determined by the very first start element.

{I}Example usage:

{I}.. code-block::

{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    with open_some_stream_over_network(...) as stream:
{I}        instance = aas_xmlization.{function_name}(
{I}            stream
{I}        )

{I}    # Do something with the ``instance``

{I}:param stream:
{II}representing an instance in XML
{I}:param has_iterparse:
{II}Module containing ``iterparse`` function.

{II}Default is to use :py:mod:`xml.etree.ElementTree` from the standard
{II}library. If you have to deal with malicious input, consider using
{II}a library such as `defusedxml.ElementTree`_.
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance read from :paramref:`stream`
{I}\"\"\"
{I}iterator = has_iterparse.iterparse(
{II}stream,
{II}['start', 'end']
{I})
{I}return from_iterparse(
{II}_with_elements_cleared_after_yield(iterator)
{I})"""
    )


def _generate_read_from_file(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the general read function to parse an instance from a file."""
    function_name = python_naming.function_name(Identifier("from_file"))

    return Stripped(
        f"""\
def {function_name}(
{I}path: PathLike,
{I}has_iterparse: HasIterparse = xml.etree.ElementTree
) -> aas_types.Class:
{I}\"\"\"
{I}Read an instance from the file at the :paramref:`path`.

{I}Example usage:

{I}.. code-block::

{I}    import pathlib
{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    path = pathlib.Path(...)
{I}    instance = aas_xmlization.{function_name}(
{I}        path
{I}    )

{I}    # Do something with the ``instance``

{I}:param path:
{II}to the file representing an instance in XML
{I}:param has_iterparse:
{II}Module containing ``iterparse`` function.

{II}Default is to use :py:mod:`xml.etree.ElementTree` from the standard
{II}library. If you have to deal with malicious input, consider using
{II}a library such as `defusedxml.ElementTree`_.
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance read from the file at :paramref:`path`
{I}\"\"\"
{I}with open(os.fspath(path), "rt", encoding='utf-8') as fid:
{II}iterator = has_iterparse.iterparse(
{III}fid,
{III}['start', 'end']
{II})
{II}return from_iterparse(
{III}_with_elements_cleared_after_yield(iterator)
{II})"""
    )


def _generate_read_from_str(
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the general read function to parse an instance from a string."""
    function_name = python_naming.function_name(Identifier("from_str"))

    return Stripped(
        f"""\
def {function_name}(
{I}text: str,
{I}has_iterparse: HasIterparse = xml.etree.ElementTree
) -> aas_types.Class:
{I}\"\"\"
{I}Read an instance from the :paramref:`text`.

{I}Example usage:

{I}.. code-block::

{I}    import pathlib
{I}    import {qualified_module_name}.xmlization as aas_xmlization

{I}    text = "<...>...</...>"
{I}    instance = aas_xmlization.{function_name}(
{I}        text
{I}    )

{I}    # Do something with the ``instance``

{I}:param text:
{II}representing an instance in XML
{I}:param has_iterparse:
{II}Module containing ``iterparse`` function.

{II}Default is to use :py:mod:`xml.etree.ElementTree` from the standard
{II}library. If you have to deal with malicious input, consider using
{II}a library such as `defusedxml.ElementTree`_.
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return:
{II}Instance read from :paramref:`text`
{I}\"\"\"
{I}iterator = has_iterparse.iterparse(
{II}io.StringIO(text),
{II}['start', 'end']
{I})
{I}return from_iterparse(
{II}_with_elements_cleared_after_yield(iterator)
{I})"""
    )


def _generate_general_read_as_element(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the general read function to dispatch on concrete classes."""
    dispatch_map = python_naming.private_constant_name(Identifier("general_dispatch"))

    body = Stripped(
        f"""\
tag_wo_ns = _parse_element_tag(element)
read_as_sequence = {dispatch_map}.get(
{I}tag_wo_ns,
{I}None
)

if read_as_sequence is None:
{I}raise DeserializationException(
{II}f"Expected the element tag to be a valid model type "
{II}f"of a concrete instance, "
{II}f"but got tag {{tag_wo_ns!r}}"
{I})

return read_as_sequence(
{I}element,
{I}iterator
)"""
    )

    return Stripped(
        f"""\
def _read_as_element(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.Class:
{I}\"\"\"
{I}Read an instance from :paramref:`iterator`, including the end element.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
{I}{indent_but_first_line(body, I)}"""
    )


_READ_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "_read_bool_from_element_text",
    intermediate.PrimitiveType.INT: "_read_int_from_element_text",
    intermediate.PrimitiveType.FLOAT: "_read_float_from_element_text",
    intermediate.PrimitiveType.STR: "_read_str_from_element_text",
    intermediate.PrimitiveType.BYTEARRAY: "_read_bytes_from_element_text",
}
assert all(
    literal in _READ_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


# fmt: off
@require(lambda arity: arity > 0)
# fmt: on
def _generate_tuple_from_element(arity: int) -> Stripped:
    """Generate the generic helper to read a tuple of ``arity`` from an element."""
    type_vars = [f"_TupleItem{i}T" for i in range(1, arity + 1)]

    parameters = ",\n".join(
        f"""\
read_item_{i}: Callable[
{I}[Element, Iterator[Tuple[str, Element]]],
{I}{type_var}
]"""
        for i, type_var in enumerate(type_vars, start=1)
    )

    param_docs = "\n".join(
        f"{I}:param read_item_{i}: "
        f"to read the item at the position {i - 1}, including its own end element"
        for i in range(1, arity + 1)
    )

    item_reads = "\n\n".join(
        f"""\
next_event_element = next(iterator, None)
if next_event_element is None:
{I}raise DeserializationException(
{II}"Expected the item {i - 1} of the tuple, but got end-of-input"
{I})

next_event, next_element = next_event_element
if next_event != 'start':
{I}raise DeserializationException(
{II}f"Expected a start element corresponding to the item {i - 1} "
{II}f"of the tuple, but got event {{next_event!r}} "
{II}f"and element {{next_element.tag!r}}"
{I})

try:
{I}item_{i} = read_item_{i}(next_element, iterator)
except DeserializationException as exception:
{I}exception.path._prepend(IndexSegment(next_element, {i - 1}))
{I}raise"""
        for i in range(1, arity + 1)
    )

    result_items = ",\n".join(f"item_{i}" for i in range(1, arity + 1))

    function_name = f"_tuple{arity}_from_element"

    return Stripped(
        f'''\
def {function_name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}{indent_but_first_line(parameters, I)}
) -> Tuple[{", ".join(type_vars)}]:
{I}"""
{I}Read a tuple of {arity} item(s) from :paramref:`iterator`.

{I}Each ``read_item_*`` function is responsible for verifying the tag of its
{I}own item element -- *e.g.*, by wrapping a scalar/enumeration reader with
{I}:py:func:`_read_v_element`, or by relying on a class's own dispatch by
{I}its natural element tag.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element enclosing the tuple
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{param_docs}
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed tuple
{I}"""
{I}if element.text is not None and len(element.text.strip()) != 0:
{II}raise DeserializationException(
{III}f"Expected only item elements and whitespace text, "
{III}f"but got text: {{element.text!r}}"
{II})

{I}{indent_but_first_line(item_reads, I)}

{I}_read_end_element(element, iterator)

{I}return (
{II}{indent_but_first_line(result_items, II)}
{I})'''
    )


def _generate_reader_and_setter(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the ``ReaderAndSetterFor{cls}``."""
    methods = []  # type: List[Stripped]

    cls_name = python_naming.class_name(cls.name)

    init_writer = io.StringIO()
    for i, prop in enumerate(cls.properties):
        prop_name = python_naming.property_name(prop.name)
        prop_type = python_common.generate_type(
            prop.type_annotation, types_module=Identifier("aas_types")
        )

        # NOTE (mristin, 2022-07-22):
        # We make all the properties optional since we switch over the properties
        # during the de-serialization.
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            if "\n" not in prop_type:
                prop_type = Stripped(f"Optional[{prop_type}]")
            else:
                # NOTE (mristin):
                # ``prop_type`` is already broken over multiple lines (see,
                # *e.g.*, the ``TupleTypeAnnotation`` case
                # in :py:func:`python_common.generate_type`), so we follow the
                # same bracket-per-line style here instead of squeezing it
                # onto one line.
                prop_type = Stripped(
                    f"""\
Optional[
{I}{indent_but_first_line(prop_type, I)}
]"""
                )

        if i > 0:
            init_writer.write("\n")
        init_writer.write(f"self.{prop_name}: {prop_type} = None")

    init_body = (
        Stripped(init_writer.getvalue())
        if len(cls.properties) > 0
        else Stripped("pass")
    )

    methods.append(
        Stripped(
            f"""\
def __init__(self) -> None:
{I}\"\"\"Initialize with all the properties unset.\"\"\"
{I}{indent_but_first_line(init_body, I)}"""
        )
    )

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_name = python_naming.property_name(prop.name)

        method_body: Stripped

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive)
        ):
            primitive_type = intermediate.try_primitive_type(type_anno)
            assert primitive_type is not None

            read_function = _READ_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type]

            method_body = Stripped(
                f"""\
self.{prop_name} = {read_function}(
{I}element,
{I}iterator
)"""
            )

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type
            if isinstance(our_type, intermediate.Enumeration):
                read_function = python_naming.private_function_name(
                    Identifier(f"read_{our_type.name}_from_element_text")
                )

                method_body = Stripped(
                    f"""\
self.{prop_name} = {read_function}(
{I}element,
{I}iterator
)"""
                )

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError(
                    f"Expected {intermediate.ConstrainedPrimitive.__name__} "
                    f"to have been handled before"
                )

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                prop_cls_name = python_naming.class_name(our_type.name)

                if len(our_type.concrete_descendants) > 0:
                    read_prop_cls_as_element = python_naming.function_name(
                        Identifier(f"_read_{our_type.name}_as_element")
                    )

                    method_body = Stripped(
                        f"""\
next_event_element = next(iterator, None)
if next_event_element is None:
{I}raise DeserializationException(
{II}"Expected a discriminator start element corresponding "
{II}"to {prop_cls_name}, but got end-of-input"
{I})

next_event, next_element = next_event_element
if next_event != 'start':
{I}raise DeserializationException(
{II}f"Expected a discriminator start element corresponding "
{II}f"to {prop_cls_name}, "
{II}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{I})

try:
{I}result = {read_prop_cls_as_element}(
{II}next_element,
{II}iterator
{I})
except DeserializationException as exception:
{I}exception.path._prepend(ElementSegment(next_element))
{I}raise

_read_end_element(element, iterator)

self.{prop_name} = result"""
                    )
                else:
                    read_prop_cls_as_sequence = python_naming.function_name(
                        Identifier(f"_read_{our_type.name}_as_sequence")
                    )

                    method_body = Stripped(
                        f"""\
self.{prop_name} = {read_prop_cls_as_sequence}(
{I}element,
{I}iterator
)"""
                    )

            elif isinstance(our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # We keep this as its own branch, separate from the
                # polymorphic-class case above, even though the code is
                # identical at the moment. We might want to support unions
                # of primitives in the future, at which point this branch
                # would need to diverge. Unlike a plain class, a named union
                # always takes the discriminator-nesting path, regardless of
                # how many implementers it flattens to.
                prop_cls_name = python_naming.class_name(our_type.name)

                read_prop_cls_as_element = python_naming.function_name(
                    Identifier(f"_read_{our_type.name}_as_element")
                )

                method_body = Stripped(
                    f"""\
next_event_element = next(iterator, None)
if next_event_element is None:
{I}raise DeserializationException(
{II}"Expected a discriminator start element corresponding "
{II}"to {prop_cls_name}, but got end-of-input"
{I})

next_event, next_element = next_event_element
if next_event != 'start':
{I}raise DeserializationException(
{II}f"Expected a discriminator start element corresponding "
{II}f"to {prop_cls_name}, "
{II}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{I})

try:
{I}result = {read_prop_cls_as_element}(
{II}next_element,
{II}iterator
{I})
except DeserializationException as exception:
{I}exception.path._prepend(ElementSegment(next_element))
{I}raise

_read_end_element(element, iterator)

self.{prop_name} = result"""
                )

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            items_primitive_type = intermediate.try_primitive_type(type_anno.items)

            if items_primitive_type is not None:
                read_item = Identifier(
                    _READ_FUNCTION_BY_PRIMITIVE_TYPE[items_primitive_type]
                )
                read_item_callable = Stripped(
                    f"""\
lambda el, it: _read_v_element(
{I}el, it, 'v', {read_item}
)"""
                )
            else:
                if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
                    raise AssertionError("Expected to handle this case before")

                elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                    if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                        read_item = python_naming.private_function_name(
                            Identifier(
                                f"read_{type_anno.items.our_type.name}_from_element_text"
                            )
                        )
                        read_item_callable = Stripped(
                            f"""\
lambda el, it: _read_v_element(
{I}el, it, 'v', {read_item}
)"""
                        )

                    elif isinstance(
                        type_anno.items.our_type, intermediate.ConstrainedPrimitive
                    ):
                        raise AssertionError("Expected to handle this case before")

                    elif isinstance(
                        type_anno.items.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        read_item = python_naming.function_name(
                            Identifier(
                                f"_read_{type_anno.items.our_type.name}_as_element"
                            )
                        )
                        read_item_callable = Stripped(read_item)

                    elif isinstance(type_anno.items.our_type, intermediate.NamedUnion):
                        # NOTE (mristin):
                        # We keep this as its own branch, separate from the
                        # class case above, even though the code is
                        # identical at the moment. We might want to support
                        # unions of primitives in the future, at which point
                        # this branch would need to diverge.
                        read_item = python_naming.function_name(
                            Identifier(
                                f"_read_{type_anno.items.our_type.name}_as_element"
                            )
                        )
                        read_item_callable = Stripped(read_item)
                    else:
                        # noinspection PyTypeChecker
                        assert_never(type_anno.items.our_type)

                else:
                    raise AssertionError(
                        "(mristin) We handle only lists of primitives types and "
                        "our types in the XML de-serialization at the moment. "
                        "The meta-model does not contain any other lists, so we wanted "
                        "to keep the code as simple as possible, and avoid unrolling. "
                        "Please contact the developers if you need this feature."
                    )

            method_body = Stripped(
                f"""\
self.{prop_name} = _read_list_of_items(
{I}element,
{I}iterator,
{I}{indent_but_first_line(read_item_callable, I)}
)"""
            )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            arity = len(type_anno.items)

            read_item_callables = []  # type: List[Stripped]
            for item_i, item_type_anno in enumerate(type_anno.items):
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    "Tuple items are restricted to atomic types (primitives, "
                    "constrained primitives, classes and enumerations) by "
                    "intermediate._translate._verify_only_simple_type_patterns, so "
                    "no nested optionals, lists or tuples are expected here."
                )

                item_primitive_type = intermediate.try_primitive_type(item_type_anno)

                # NOTE (mristin):
                # Class items are dispatched through their own natural element tag, so
                # their read function already verifies the tag. Atomic (primitive or
                # enumeration) items, on the other hand, are always wrapped in
                # a positional ``<v1>``, ``<v2>``, *etc.* element, so we have to
                # verify that tag ourselves.
                item_is_v_element = True

                if item_primitive_type is not None:
                    read_item = Identifier(
                        _READ_FUNCTION_BY_PRIMITIVE_TYPE[item_primitive_type]
                    )
                elif isinstance(item_type_anno, intermediate.PrimitiveTypeAnnotation):
                    raise AssertionError("Expected to handle this case before")

                elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                    if isinstance(item_type_anno.our_type, intermediate.Enumeration):
                        read_item = python_naming.private_function_name(
                            Identifier(
                                f"read_{item_type_anno.our_type.name}"
                                f"_from_element_text"
                            )
                        )

                    elif isinstance(
                        item_type_anno.our_type, intermediate.ConstrainedPrimitive
                    ):
                        raise AssertionError("Expected to handle this case before")

                    elif isinstance(
                        item_type_anno.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        item_is_v_element = False
                        read_item = python_naming.function_name(
                            Identifier(
                                f"_read_{item_type_anno.our_type.name}_as_element"
                            )
                        )

                    elif isinstance(item_type_anno.our_type, intermediate.NamedUnion):
                        # NOTE (mristin):
                        # We keep this as its own branch, separate from the
                        # class case above, even though the code is
                        # identical at the moment. We might want to support
                        # unions of primitives in the future, at which point
                        # this branch would need to diverge.
                        item_is_v_element = False
                        read_item = python_naming.function_name(
                            Identifier(
                                f"_read_{item_type_anno.our_type.name}_as_element"
                            )
                        )

                    else:
                        # noinspection PyTypeChecker
                        assert_never(item_type_anno.our_type)
                else:
                    # noinspection PyTypeChecker
                    assert_never(item_type_anno)

                if item_is_v_element:
                    v_name = f"v{item_i + 1}"
                    read_item_callables.append(
                        Stripped(
                            f"""\
lambda el, it: _read_v_element(
{I}el, it, "{v_name}", {read_item}
)"""
                        )
                    )
                else:
                    read_item_callables.append(Stripped(read_item))

            joined_read_item_callables = ",\n".join(read_item_callables)

            method_body = Stripped(
                f"""\
self.{prop_name} = _tuple{arity}_from_element(
{I}element,
{I}iterator,
{I}{indent_but_first_line(joined_read_item_callables, I)}
)"""
            )

        else:
            assert_never(type_anno)

        method_name = python_naming.method_name(Identifier(f"read_and_set_{prop.name}"))
        methods.append(
            Stripped(
                f"""\
def {method_name}(
{I}self,
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> None:
{I}\"\"\"
{I}Read :paramref:`element` as the property
{I}:py:attr:`.types.{cls_name}.{prop_name}` and set it.
{I}\"\"\"
{I}{indent_but_first_line(method_body, I)}"""
            )
        )

    reader_and_setter_name = python_naming.private_class_name(
        Identifier(f"Reader_and_setter_for_{cls.name}")
    )

    writer = io.StringIO()
    writer.write(
        f"""\
class {reader_and_setter_name}:
{I}\"\"\"
{I}Provide a buffer for reading and setting the properties for the class
{I}:py:class:`{cls_name}`.

{I}The properties correspond to the constructor arguments of
{I}:py:class:`{cls_name}`. We use this buffer to facilitate dispatching when
{I}parsing the properties in a streaming fashion.
{I}\"\"\""""
    )

    for method in methods:
        writer.write("\n\n")
        writer.write(textwrap.indent(method, I))

    return Stripped(writer.getvalue())


def _generate_read_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the method to read the instance as sequence of XML-encoded properties.

    This function performs no dispatch! The dispatch is expected to have been
    performed already based on the discriminator element.

    The properties are expected to correspond to the constructor arguments of
    the ``cls``.
    """
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
                (prop.name, str(prop.type_annotation))
                for prop in cls.properties
            )
    ), (
        "(mristin, 2022-10-11) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    blocks = [
        Stripped(
            f"""\
if element.text is not None and len(element.text.strip()) != 0:
{I}raise DeserializationException(
{II}f"Expected only XML elements representing the properties and whitespace text, "
{II}f"but got text: {{element.text!r}}"
{I})"""
        ),
        Stripped("_raise_if_has_tail_or_attrib(element)"),
    ]  # type: List[Stripped]

    # region Body

    cls_name = python_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        blocks.append(
            Stripped(
                f"""\
next_event_element = next(iterator, None)
if next_event_element is None:
{I}raise DeserializationException(
{II}f"Expected the end element corresponding to {{element.tag}}, "
{II}f"but got the end-of-input"
{I})

next_event, next_element = next_event_element
if next_event != 'end' or next_element.tag != element.tag:
{I}raise DeserializationException(
{II}f"Expected the end element corresponding to {{element.tag}}, "
{II}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{I})"""
            )
        )

        blocks.append(Stripped(f"return aas_types.{cls_name}()"))
    else:
        reader_and_setter_name = python_naming.private_class_name(
            Identifier(f"Reader_and_setter_for_{cls.name}")
        )

        read_and_set_dispatch_name = python_naming.private_constant_name(
            Identifier(f"read_and_set_dispatch_for_{cls.name}")
        )

        blocks.append(
            Stripped(
                f"""\
reader_and_setter = (
{I}{reader_and_setter_name}()
)

while True:
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}"Expected one or more XML-encoded properties or the end element, "
{III}"but got the end-of-input"
{II})

{I}next_event, next_element = next_event_element
{I}if next_event == 'end' and next_element.tag == element.tag:
{II}# We reached the end element enclosing the sequence.
{II}break

{I}if next_event != 'start':
{II}raise DeserializationException(
{III}"Expected a start element corresponding to a property, "
{III}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{II})

{I}try:
{II}tag_wo_ns = _parse_element_tag(next_element)
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(next_element))
{II}raise

{I}read_and_set_method = {read_and_set_dispatch_name}.get(
{II}tag_wo_ns,
{II}None
{I})
{I}if read_and_set_method is None:
{II}an_exception = DeserializationException(
{III}f"Expected an element representing a property, "
{III}f"but got an element with unexpected tag: {{tag_wo_ns!r}}"
{II})
{II}an_exception.path._prepend(ElementSegment(next_element))
{II}raise an_exception

{I}try:
{II}read_and_set_method(
{III}reader_and_setter,
{III}next_element,
{III}iterator
{II})
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(next_element))
{II}raise"""
            )
        )

        for i, prop in enumerate(cls.properties):
            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                continue

            prop_name = python_naming.property_name(prop.name)

            cause_literal = python_common.string_literal(
                f"The required property {prop.xml_name!r} is missing"
            )
            blocks.append(
                Stripped(
                    f"""\
if reader_and_setter.{prop_name} is None:
{I}raise DeserializationException(
{II}{cause_literal}
{I})"""
                )
            )

        init_writer = io.StringIO()
        init_writer.write(f"return aas_types.{cls_name}(\n")

        for i, arg in enumerate(cls.constructor.arguments):
            prop = cls.properties_by_name[arg.name]

            prop_name = python_naming.property_name(prop.name)

            init_writer.write(f"{I}reader_and_setter.{prop_name}")

            if i < len(cls.constructor.arguments) - 1:
                init_writer.write(",\n")
            else:
                init_writer.write("\n")

        init_writer.write(")")

        blocks.append(Stripped(init_writer.getvalue()))

    # endregion

    function_name = python_naming.private_function_name(
        Identifier(f"read_{cls.name}_as_sequence")
    )

    writer = io.StringIO()
    writer.write(
        f"""\
def {function_name}(
{II}element: Element,
{II}iterator: Iterator[Tuple[str, Element]]
) -> aas_types.{cls_name}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{cls_name}`
{I}as a sequence of XML-encoded properties.

{I}The end element corresponding to the :paramref:`element` will be
{I}read as well.

{I}:param element: start element, parent of the sequence
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    return Stripped(writer.getvalue())


@require(
    lambda cls: len(cls.concrete_descendants) > 0,
    "Expected the class to have concrete descendants; "
    "otherwise it makes no sense to dispatch",
)
def _generate_dispatch_map_for_class(
    cls: Union[intermediate.AbstractClass, intermediate.ConcreteClass]
) -> Stripped:
    """Generate the mapping model type 🠒 read-as-sequence function."""
    mapping_name = python_naming.private_constant_name(
        Identifier(f"dispatch_for_{cls.name}")
    )

    mapping_writer = io.StringIO()

    cls_name = python_naming.class_name(cls.name)
    if isinstance(cls, intermediate.AbstractClass):
        mapping_writer.write(
            f"""\
#: Dispatch XML class names to read-as-sequence functions
#: corresponding to concrete descendants of {cls_name}
"""
        )
    else:
        mapping_writer.write(
            f"""\
#: Dispatch XML class names to read-as-sequence functions
#: corresponding to {cls_name} and its concrete descendants
"""
        )

    cls_name = python_naming.class_name(cls.name)

    mapping_writer.write(
        f"""\
{mapping_name}: Mapping[
{I}str,
{I}Callable[
{II}[
{III}Element,
{III}Iterator[Tuple[str, Element]]
{II}],
{II}aas_types.{cls_name}
{I}]
] = {{
"""
    )

    dispatch_classes = list(cls.concrete_descendants)

    # NOTE (mristin, 2022-10-11):
    # In case of concrete classes, we have to consider also dispatching to their
    # own read function as ``concrete_descendants`` *exclude* the concrete class
    # itself.
    if isinstance(cls, intermediate.ConcreteClass):
        dispatch_classes.insert(0, cls)

    for dispatch_class in dispatch_classes:
        read_as_sequence_name = python_naming.private_function_name(
            Identifier(f"read_{dispatch_class.name}_as_sequence")
        )

        xml_name_literal = python_common.string_literal(
            naming.xml_class_name(dispatch_class.name)
        )

        mapping_writer.write(
            f"""\
{I}{xml_name_literal}: {read_as_sequence_name},
"""
        )

    mapping_writer.write("}")

    return Stripped(mapping_writer.getvalue())


def _generate_general_dispatch_map(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the general mapping model type 🠒 read-as-sequence function."""
    mapping_name = python_naming.private_constant_name(Identifier("general_dispatch"))

    mapping_writer = io.StringIO()

    mapping_writer.write(
        """\
#: Dispatch XML class names to read-as-sequence functions
#: corresponding to the concrete classes
"""
    )

    mapping_writer.write(
        f"""\
{mapping_name}: Mapping[
{I}str,
{I}Callable[
{II}[
{III}Element,
{III}Iterator[Tuple[str, Element]]
{II}],
{II}aas_types.Class
{I}]
] = {{
"""
    )

    for concrete_cls in symbol_table.concrete_classes:
        read_as_sequence_name = python_naming.private_function_name(
            Identifier(f"read_{concrete_cls.name}_as_sequence")
        )

        xml_name_literal = python_common.string_literal(
            naming.xml_class_name(concrete_cls.name)
        )

        mapping_writer.write(
            f"""\
{I}{xml_name_literal}: {read_as_sequence_name},
"""
        )

    mapping_writer.write("}")

    return Stripped(mapping_writer.getvalue())


def _generate_reader_and_setter_map(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the mapping property name 🠒 read function."""
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
                (prop.name, str(prop.type_annotation))
                for prop in cls.properties
            )
    ), (
        "(mristin, 2022-10-11) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    identifiers_expressions = []  # type: List[Tuple[str, Stripped]]

    reader_and_setter_cls_name = python_naming.private_class_name(
        Identifier(f"Reader_and_setter_for_{cls.name}")
    )

    for prop in cls.properties:
        xml_identifier = prop.xml_name
        method_name = python_naming.method_name(Identifier(f"read_and_set_{prop.name}"))

        identifiers_expressions.append(
            (xml_identifier, Stripped(f"{reader_and_setter_cls_name}.{method_name}"))
        )

    map_name = python_naming.private_constant_name(
        Identifier(f"read_and_set_dispatch_for_{cls.name}")
    )

    writer = io.StringIO()
    writer.write(
        f"""\
#: Dispatch XML property name to read & set method in
#: :py:class:`{reader_and_setter_cls_name}`
{map_name}: Mapping[
{I}str,
{I}Callable[
{II}[
{III}{reader_and_setter_cls_name},
{III}Element,
{III}Iterator[Tuple[str, Element]]
{II}],
{II}None
{I}]
] = {{
"""
    )
    for identifier, expression in identifiers_expressions:
        writer.write(
            f"""\
{I}{python_common.string_literal(identifier)}:
{II}{indent_but_first_line(expression, II)},
"""
        )

    writer.write("}")
    return Stripped(writer.getvalue())


_WRITE_METHOD_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "_write_bool_as_element",
    intermediate.PrimitiveType.INT: "_write_int_as_element",
    intermediate.PrimitiveType.FLOAT: "_write_float_as_element",
    intermediate.PrimitiveType.STR: "_write_str_as_element",
    intermediate.PrimitiveType.BYTEARRAY: "_write_bytes_as_element",
}
assert all(
    literal in _WRITE_METHOD_BY_PRIMITIVE_TYPE for literal in intermediate.PrimitiveType
)


def _count_required_properties(cls: intermediate.Class) -> int:
    """Count the number of properties which are marked as non-optional."""
    return sum(
        1
        for prop in cls.properties
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
    )


# fmt: off
@require(
    lambda prop:
    (
        type_anno := intermediate.beneath_optional(prop.type_annotation),
        isinstance(type_anno, intermediate.OurTypeAnnotation)
        and isinstance(type_anno.our_type, intermediate.ConcreteClass)
        and len(type_anno.our_type.concrete_descendants) == 0
    )[1],
    "We expect the property to be of a concrete class with no descendants so that "
    "its value can be represented as a sequence of XML elements, each corresponding "
    "to a property of the value."
)
# fmt: on
def _generate_snippet_for_writing_concrete_cls_prop(
    prop: intermediate.Property,
) -> Stripped:
    """Generate code snippet to write a class property as a sequence."""
    type_anno = intermediate.beneath_optional(prop.type_annotation)
    assert isinstance(type_anno, intermediate.OurTypeAnnotation)

    our_type = type_anno.our_type
    assert isinstance(our_type, intermediate.ConcreteClass)

    xml_prop_literal = python_common.string_literal(prop.xml_name)

    write_cls_as_sequence = python_naming.private_method_name(
        Identifier(f"write_{our_type.name}_as_sequence")
    )

    prop_name = python_naming.property_name(prop.name)

    if _count_required_properties(our_type) > 0:
        return Stripped(
            f"""\
self._write_start_element({xml_prop_literal})
self.{write_cls_as_sequence}(
{I}that.{prop_name}
)
self._write_end_element({xml_prop_literal})"""
        )

    # NOTE (mristin, 2022-10-14):
    # Prefix with "the" so that we avoid naming conflicts.
    variable = python_naming.variable_name(Identifier(f"the_{prop.name}"))

    writer = io.StringIO()
    writer.write(f"{variable} = that.{prop_name}\n")

    conjunction = [
        f"{variable}.{python_naming.property_name(prop.name)} is None"
        for prop in our_type.properties
    ]

    writer.write(
        """\
# We optimize for the case where all the optional properties are not set,
# so that we can simply output an empty element.
if (
"""
    )
    for i, expr in enumerate(conjunction):
        if i > 0:
            writer.write(f"{II}and {indent_but_first_line(expr, II)}\n")
        else:
            writer.write(f"{II}{indent_but_first_line(expr, II)}\n")

    writer.write(
        f"""\
):
{I}self._write_empty_element(
{II}{xml_prop_literal}
{I})
else:
{I}self._write_start_element({xml_prop_literal})
{I}self.{write_cls_as_sequence}(
{II}{variable}
{I})
{I}self._write_end_element({xml_prop_literal})"""
    )

    return Stripped(writer.getvalue())


def _generate_write_cls_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the method to serialize the ``cls`` as a sequence of XML elements.

    The elements correspond to the properties of the ``cls``.

    The generated method lives in the ``_Serializer`` class.
    """
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
        (prop.name, str(prop.type_annotation))
        for prop in cls.properties
    )
    ), (
        "(mristin, 2022-10-14) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    body_blocks = []  # type: List[Stripped]

    if len(cls.properties) == 0:
        body_blocks.append(
            Stripped(
                """\
# There are no properties specified for this class, so nothing can be written.
return"""
            )
        )
    else:
        for prop in cls.properties:
            prop_name = python_naming.property_name(prop.name)
            xml_prop_literal = python_common.string_literal(prop.xml_name)

            type_anno = intermediate.beneath_optional(prop.type_annotation)

            primitive_type = intermediate.try_primitive_type(type_anno)

            write_prop: Stripped

            if primitive_type is not None:
                write_method = _WRITE_METHOD_BY_PRIMITIVE_TYPE[primitive_type]

                write_prop = Stripped(
                    f"""\
self.{write_method}(
{I}{xml_prop_literal},
{I}that.{prop_name}
)"""
                )
            else:
                assert not isinstance(type_anno, intermediate.PrimitiveTypeAnnotation)

                if isinstance(type_anno, intermediate.OurTypeAnnotation):
                    our_type = type_anno.our_type
                    if isinstance(our_type, intermediate.Enumeration):
                        write_prop = Stripped(
                            f"""\
self._write_str_as_element(
{I}{xml_prop_literal},
{I}that.{prop_name}.value
)"""
                        )

                    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                        raise AssertionError("Expected to be handled before")

                    elif isinstance(
                        our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        if len(our_type.concrete_descendants) > 0:
                            write_prop = Stripped(
                                f"""\
self._write_start_element({xml_prop_literal})
self.visit(that.{prop_name})
self._write_end_element({xml_prop_literal})"""
                            )
                        else:
                            assert isinstance(our_type, intermediate.ConcreteClass), (
                                f"Unexpected abstract class with no concrete "
                                f"descendants: {our_type.name!r}"
                            )

                            # NOTE (mristin, 2022-10-14):
                            # We have to put the code in a separate function as it
                            # became barely readable *this* indented.
                            write_prop = (
                                _generate_snippet_for_writing_concrete_cls_prop(
                                    prop=prop
                                )
                            )

                    elif isinstance(our_type, intermediate.NamedUnion):
                        # NOTE (mristin):
                        # We keep this as its own branch, separate from the
                        # polymorphic-class case above, even though the code
                        # is identical at the moment. We might want to
                        # support unions of primitives in the future, at
                        # which point this branch would need to diverge.
                        # Unlike a plain class, a named union always takes
                        # the discriminator-nesting path.
                        write_prop = Stripped(
                            f"""\
self._write_start_element({xml_prop_literal})
self.visit(that.{prop_name})
self._write_end_element({xml_prop_literal})"""
                        )

                    else:
                        assert_never(our_type)

                elif isinstance(type_anno, intermediate.ListTypeAnnotation):
                    items_primitive_type = intermediate.try_primitive_type(
                        type_anno.items
                    )

                    if items_primitive_type is not None:
                        write_method = _WRITE_METHOD_BY_PRIMITIVE_TYPE[
                            items_primitive_type
                        ]
                        write_prop = Stripped(
                            f"""\
self._write_list_of_items(
{I}{xml_prop_literal},
{I}that.{prop_name},
{I}lambda v: self.{write_method}(
{II}'v', v
{I})
)"""
                        )
                    else:
                        if isinstance(
                            type_anno.items, intermediate.PrimitiveTypeAnnotation
                        ):
                            raise AssertionError("Expected to be handled before")

                        elif isinstance(
                            type_anno.items, intermediate.OurTypeAnnotation
                        ):
                            if isinstance(
                                type_anno.items.our_type, intermediate.Enumeration
                            ):
                                write_prop = Stripped(
                                    f"""\
self._write_list_of_items(
{I}{xml_prop_literal},
{I}that.{prop_name},
{I}lambda v: self._write_str_as_element(
{II}'v', v.value
{I})
)"""
                                )

                            elif isinstance(
                                type_anno.items.our_type,
                                intermediate.ConstrainedPrimitive,
                            ):
                                raise AssertionError("Expected to be handled before")

                            elif isinstance(
                                type_anno.items.our_type,
                                (
                                    intermediate.AbstractClass,
                                    intermediate.ConcreteClass,
                                ),
                            ):
                                write_prop = Stripped(
                                    f"""\
self._write_list_of_items(
{I}{xml_prop_literal},
{I}that.{prop_name},
{I}self.visit
)"""
                                )

                            elif isinstance(
                                type_anno.items.our_type, intermediate.NamedUnion
                            ):
                                # NOTE (mristin):
                                # We keep this as its own branch, separate
                                # from the class case above, even though the
                                # code is identical at the moment. We might
                                # want to support unions of primitives in
                                # the future, at which point this branch
                                # would need to diverge.
                                write_prop = Stripped(
                                    f"""\
self._write_list_of_items(
{I}{xml_prop_literal},
{I}that.{prop_name},
{I}self.visit
)"""
                                )

                            else:
                                # noinspection PyTypeChecker
                                assert_never(type_anno.items.our_type)

                        else:
                            raise NotImplementedError(
                                f"(mristin) We currently generate only "
                                f"the XML serialization for lists of primitive types "
                                f"and our types, but you supplied the following "
                                f"type: {type_anno}. "
                                f"Please contact the developers if you need this feature."
                            )

                elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                    item_write_stmts = []  # type: List[Stripped]
                    for i, item_type_anno in enumerate(type_anno.items):
                        assert isinstance(
                            item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                        ), (
                            "Tuple items are restricted to atomic types "
                            "(primitives, constrained primitives, classes and "
                            "enumerations) by "
                            "intermediate._translate._verify_only_simple_type_patterns"
                            ", so no nested optionals, lists or tuples are expected "
                            "here."
                        )

                        item_access = f"that.{prop_name}[{i}]"
                        item_xml_literal = python_common.string_literal(f"v{i + 1}")

                        item_primitive_type = intermediate.try_primitive_type(
                            item_type_anno
                        )

                        if item_primitive_type is not None:
                            write_method = _WRITE_METHOD_BY_PRIMITIVE_TYPE[
                                item_primitive_type
                            ]
                            item_write_stmts.append(
                                Stripped(
                                    f"""\
self.{write_method}(
{I}{item_xml_literal},
{I}{item_access}
)"""
                                )
                            )

                        elif isinstance(
                            item_type_anno, intermediate.PrimitiveTypeAnnotation
                        ):
                            raise AssertionError("Expected to be handled before")

                        elif isinstance(item_type_anno, intermediate.OurTypeAnnotation):
                            if isinstance(
                                item_type_anno.our_type, intermediate.Enumeration
                            ):
                                item_write_stmts.append(
                                    Stripped(
                                        f"""\
self._write_str_as_element(
{I}{item_xml_literal},
{I}{item_access}.value
)"""
                                    )
                                )

                            elif isinstance(
                                item_type_anno.our_type,
                                intermediate.ConstrainedPrimitive,
                            ):
                                raise AssertionError("Expected to be handled before")

                            elif isinstance(
                                item_type_anno.our_type,
                                (
                                    intermediate.AbstractClass,
                                    intermediate.ConcreteClass,
                                ),
                            ):
                                # NOTE (mristin):
                                # Unlike primitives, constrained primitives and
                                # enumeration literals, a class writes its own
                                # element tag through ``self.visit``, exactly
                                # as we do for the lists above.
                                item_write_stmts.append(
                                    Stripped(f"self.visit({item_access})")
                                )

                            elif isinstance(
                                item_type_anno.our_type, intermediate.NamedUnion
                            ):
                                # NOTE (mristin):
                                # We keep this as its own branch, separate
                                # from the class case above, even though the
                                # code is identical at the moment. We might
                                # want to support unions of primitives in
                                # the future, at which point this branch
                                # would need to diverge.
                                item_write_stmts.append(
                                    Stripped(f"self.visit({item_access})")
                                )

                            else:
                                # noinspection PyTypeChecker
                                assert_never(item_type_anno.our_type)
                        else:
                            # noinspection PyTypeChecker
                            assert_never(item_type_anno)

                    item_write_stmts_joined = "\n".join(item_write_stmts)

                    write_prop = Stripped(
                        f"""\
self._write_start_element({xml_prop_literal})
{item_write_stmts_joined}
self._write_end_element({xml_prop_literal})"""
                    )

                else:
                    assert_never(type_anno)

            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                write_prop = Stripped(
                    f"""\
if that.{prop_name} is not None:
{I}{indent_but_first_line(write_prop, I)}"""
                )

            body_blocks.append(write_prop)

    cls_name = python_naming.class_name(cls.name)
    function_name = python_naming.private_method_name(
        Identifier(f"write_{cls.name}_as_sequence")
    )

    writer = io.StringIO()
    writer.write(
        f"""\
def {function_name}(
{I}self,
{I}that: aas_types.{cls_name}
) -> None:
{I}\"\"\"
{I}Serialize :paramref:`that` to :py:attr:`~stream` as a sequence of
{I}XML elements.

{I}Each element in the sequence corresponds to a property. If no properties
{I}are set, nothing is written to the :py:attr:`~stream`.

{I}:param that: instance to be serialized
{I}\"\"\"
"""
    )

    for i, body_block in enumerate(body_blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(body_block, I))

    return Stripped(writer.getvalue())


def _generate_visit_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the method to serialize the ``cls`` as an XML element.

    The generated method lives in the ``_Serializer`` class.
    """
    # fmt: off
    assert (
            sorted(
                (arg.name, str(arg.type_annotation))
                for arg in cls.constructor.arguments
            ) == sorted(
        (prop.name, str(prop.type_annotation))
        for prop in cls.properties
    )
    ), (
        "(mristin, 2022-10-11) We assume that the properties and constructor arguments "
        "are identical at this point. If this is not the case, we have to re-write the "
        "logic substantially! Please contact the developers if you see this."
    )
    # fmt: on

    xml_cls_literal = python_common.string_literal(naming.xml_class_name(cls.name))

    body_blocks = []  # type: List[Stripped]

    if len(cls.properties) == 0:
        body_blocks.append(
            Stripped(
                f"""\
self._write_empty_element(
{I}{xml_cls_literal}
)"""
            )
        )
    else:
        write_cls_as_sequence = python_naming.private_method_name(
            Identifier(f"write_{cls.name}_as_sequence")
        )

        if _count_required_properties(cls) > 0:
            body_blocks.append(
                Stripped(
                    f"""\
self._write_start_element({xml_cls_literal})
self.{write_cls_as_sequence}(
{I}that
)
self._write_end_element({xml_cls_literal})"""
                )
            )
        else:
            # NOTE (mristin, 2022-10-14):
            # We optimize for the case where all the optional properties are not set,
            # so that we can simply output an empty element.
            conjunction = [
                f"that.{python_naming.property_name(prop.name)} is None"
                for prop in cls.properties
            ]

            if_empty_writer = io.StringIO()
            if_empty_writer.write(
                """\
# We optimize for the case where all the optional properties are not set,
# so that we can simply output an empty element.
if (
"""
            )
            for i, expr in enumerate(conjunction):
                if i > 0:
                    if_empty_writer.write(
                        f"{II}and {indent_but_first_line(expr, II)}\n"
                    )
                else:
                    if_empty_writer.write(f"{II}{indent_but_first_line(expr, II)}\n")

            if_empty_writer.write(
                f"""\
):
{I}self._write_empty_element(
{II}{xml_cls_literal}
{I})
else:
{I}self._write_start_element({xml_cls_literal})
{I}self.{write_cls_as_sequence}(
{II}that
{I})
{I}self._write_end_element({xml_cls_literal})"""
            )

            body_blocks.append(Stripped(if_empty_writer.getvalue()))

    cls_name = python_naming.class_name(cls.name)
    visit_name = python_naming.method_name(Identifier(f"visit_{cls.name}"))

    writer = io.StringIO()
    writer.write(
        f"""\
def {visit_name}(
{I}self,
{I}that: aas_types.{cls_name}
) -> None:
{I}\"\"\"
{I}Serialize :paramref:`that` to :py:attr:`~stream` as an XML element.

{I}The enclosing XML element designates the class of the instance, where its
{I}children correspond to the properties of the instance.

{I}:param that: instance to be serialized
{I}\"\"\"
"""
    )

    for i, body_block in enumerate(body_blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(body_block, I))

    return Stripped(writer.getvalue())


# fmt: off
@require(
    lambda symbol_table:
    '"' not in symbol_table.meta_model.xml_namespace,
    "No single quotes expected in the XML namespace so that we can directly "
    "write the namespace as-is"
)
# fmt: on
def _generate_serializer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the serializer as a visitor which writes to a stream on visits."""
    body_blocks = [
        Stripped(
            """\
#: Stream to be written to when we visit the instances
stream: Final[TextIO]"""
        ),
        Stripped(
            f"""\
#: Method pointer to be invoked for writing the start element with or without
#: specifying a namespace (depending on the state of the serializer)
_write_start_element: Callable[
{I}[str],
{I}None
]"""
        ),
        Stripped(
            f"""\
#: Method pointer to be invoked for writing an empty element with or without
#: specifying a namespace (depending on the state of the serializer)
_write_empty_element: Callable[
{I}[str],
{I}None
]"""
        ),
        Stripped(
            """\
# NOTE (mristin, 2022-10-14):
# The serialization procedure is quite rigid. We leverage the specifics of
# the serialization procedure to optimize the code a bit.
#
# Namely, we model the writing of the XML elements as a state machine.
# The namespace is only specified for the very first element. All the subsequent
# elements will *not* have the namespace specified. We implement that behavior by
# using pointers to methods, as Python treats the methods as first-class citizens.
#
# The ``_write_start_element`` will point to
# ``_write_first_start_element_with_namespace`` on the *first* invocation.
# Afterwards, it will be redirected to ``_write_start_element_without_namespace``.
#
# Analogously for ``_write_empty_element``.
#
# Please see the implementation for the details, but this should give you at least
# a rough overview."""
        ),
        Stripped(
            f"""\
def _write_first_start_element_with_namespace(
{II}self,
{II}name: str
) -> None:
{I}\"\"\"
{I}Write the start element with the tag name :paramref:`name` and specify
{I}its namespace.

{I}The :py:attr:`~_write_start_element` is set to
{I}:py:meth:`~_write_start_element_without_namespace` after the first invocation
{I}of this method.

{I}:param name: of the element tag. Expected to contain no XML special characters.
{I}\"\"\"
{I}self.stream.write(f'<{{name}} xmlns="{{NAMESPACE}}">')

{I}# NOTE (mristin, 2022-10-14):
{I}# Any subsequence call to `_write_start_element` or `_write_empty_element`
{I}# should not specify the namespace of the element as we specified now already
{I}# specified it.
{I}self._write_start_element = self._write_start_element_without_namespace
{I}self._write_empty_element = self._write_empty_element_without_namespace"""
        ),
        Stripped(
            f"""\
def _write_start_element_without_namespace(
{II}self,
{II}name: str
) -> None:
{I}\"\"\"
{I}Write the start element with the tag name :paramref:`name`.

{I}The first element, written *before* this one, is expected to have been
{I}already written with the namespace specified.

{I}:param name: of the element tag. Expected to contain no XML special characters.
{I}\"\"\"
{I}self.stream.write(f'<{{name}}>')"""
        ),
        Stripped(
            f"""\
def _escape_and_write_text(
{II}self,
{II}text: str
) -> None:
{I}\"\"\"
{I}Escape :paramref:`text` for XML and write it.

{I}:param text: to be escaped and written
{I}\"\"\"
{I}# NOTE (mristin, 2022-10-14):
{I}# We ran ``timeit`` on manual code which escaped XML special characters with
{I}# a dictionary, and on another snippet which called three ``.replace()``.
{I}# The code with ``.replace()`` was an order of magnitude faster on our computers.
{I}self.stream.write(
{II}text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
{I})"""
        ),
        Stripped(
            f"""\
def _write_end_element(
{II}self,
{II}name: str
) -> None:
{I}\"\"\"
{I}Write the end element with the tag name :paramref:`name`.

{I}:param name: of the element tag. Expected to contain no XML special characters.
{I}\"\"\"
{I}self.stream.write(f'</{{name}}>')"""
        ),
        Stripped(
            f"""\
def _write_first_empty_element_with_namespace(
{II}self,
{II}name: str
) -> None:
{I}\"\"\"
{I}Write the first (and only) empty element with the tag name :paramref:`name`.

{I}No elements are expected to be written to the stream afterwards. The element
{I}includes the namespace specification.

{I}:param name: of the element tag. Expected to contain no XML special characters.
{I}\"\"\"
{I}self.stream.write(f'<{{name}} xmlns="{{NAMESPACE}}"/>')
{I}self._write_empty_element = self._rase_if_write_element_called_again
{I}self._write_start_element = self._rase_if_write_element_called_again"""
        ),
        Stripped(
            f"""\
def _rase_if_write_element_called_again(
{II}self,
{II}name: str
) -> None:
{I}raise AssertionError(
{II}f"We expected to call ``_write_first_empty_element_with_namespace`` "
{II}f"only once. This is an unexpected second call for writing "
{II}f"an (empty or non-empty) element with the tag name: {{name!r}}"
{I})"""
        ),
        Stripped(
            f"""\
def _write_empty_element_without_namespace(
{II}self,
{II}name: str
) -> None:
{I}\"\"\"
{I}Write the empty element with the tag name :paramref:`name`.

{I}The call to this method is expected to occur *after* the enclosing element with
{I}a specified namespace has been written.

{I}:param name: of the element tag. Expected to contain no XML special characters.
{I}\"\"\"
{I}self.stream.write(f'<{{name}}/>')"""
        ),
        Stripped(
            f"""\
def _write_bool_as_element(
{II}self,
{II}name: str,
{II}value: bool
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a boolean enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param value: to be serialized
{I}\"\"\"
{I}self._write_start_element(name)
{I}self.stream.write('true' if value else 'false')
{I}self._write_end_element(name)"""
        ),
        Stripped(
            f"""\
def _write_int_as_element(
{II}self,
{II}name: str,
{II}value: int
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of an integer enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param value: to be serialized
{I}\"\"\"
{I}self._write_start_element(name)
{I}self.stream.write(str(value))
{I}self._write_end_element(name)"""
        ),
        Stripped(
            f"""\
def _write_float_as_element(
{II}self,
{II}name: str,
{II}value: float
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a floating-point number enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param value: to be serialized
{I}\"\"\"
{I}self._write_start_element(name)

{I}if value == math.inf:
{II}self.stream.write('INF')
{I}elif value == -math.inf:
{II}self.stream.write('-INF')
{I}elif math.isnan(value):
{II}self.stream.write('NaN')
{I}elif value == 0:
{II}if math.copysign(1.0, value) < 0.0:
{III}self.stream.write('-0.0')
{II}else:
{III}self.stream.write('0.0')
{I}else:
{II}self.stream.write(str(value))

{I}self._write_end_element(name)"""
        ),
        Stripped(
            f"""\
def _write_str_as_element(
{II}self,
{II}name: str,
{II}value: str
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a string enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param value: to be serialized
{I}\"\"\"
{I}self._write_start_element(name)
{I}self._escape_and_write_text(value)
{I}self._write_end_element(name)"""
        ),
        Stripped(
            f"""\
def _write_bytes_as_element(
{II}self,
{II}name: str,
{II}value: bytes
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a binary content enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param value: to be serialized
{I}\"\"\"
{I}self._write_start_element(name)

{I}# NOTE (mristin):
{I}# We need to decode the result of the base64-encoding to ASCII since we are
{I}# writing to an XML *text* stream. ``base64.b64encode(.)`` gives us bytes,
{I}# not a string.
{I}encoded = base64.b64encode(value).decode('ascii')

{I}# NOTE (mristin):
{I}# Base64 alphabet excludes ``<``, ``>`` and ``&``, so we can directly
{I}# write the ``encoded`` content to the stream as XML text.
{I}#
{I}# See: https://datatracker.ietf.org/doc/html/rfc4648#section-4
{I}self.stream.write(encoded)
{I}self._write_end_element(name)"""
        ),
        Stripped(
            f"""\
def _write_list_of_items(
{I}self,
{I}name: str,
{I}items: Sequence[_ItemT],
{I}write_item: Callable[[_ItemT], None]
) -> None:
{I}\"\"\"
{I}Write :paramref:`items` enclosed in the :paramref:`name` element.

{I}:param name: of the enclosing element
{I}:param items: to be written
{I}:param write_item:
{II}to write a single item of :paramref:`items` -- either into its own
{II}``v`` element (for scalars/enumerations) or its own natural class
{II}element (for classes, via :py:meth:`~visit`)
{I}\"\"\"
{I}if len(items) == 0:
{II}self._write_empty_element(name)
{I}else:
{II}self._write_start_element(name)
{II}for item in items:
{III}write_item(item)
{II}self._write_end_element(name)"""
        ),
        Stripped(
            f"""\
def __init__(
{I}self,
{I}stream: TextIO
) -> None:
{I}\"\"\"
{I}Initialize the visitor to write to :paramref:`stream`.

{I}The first element will include the :py:attr:`~.NAMESPACE`. Every other
{I}element will not have the namespace specified.

{I}:param stream: where to write to
{I}\"\"\"
{I}self.stream = stream
{I}self._write_start_element = (
{II}self._write_first_start_element_with_namespace
{I})
{I}self._write_empty_element = (
{II}self._write_first_empty_element_with_namespace
{I})"""
        ),
    ]

    for cls in symbol_table.concrete_classes:
        body_blocks.append(_generate_write_cls_as_sequence(cls=cls))
        body_blocks.append(_generate_visit_cls(cls=cls))

    writer = io.StringIO()
    writer.write(
        Stripped(
            f"""\
class _Serializer(aas_types.AbstractVisitor):
{I}\"\"\"Encode instances as XML and write them to :py:attr:`~stream`.\"\"\""""
        )
    )

    for body_block in body_blocks:
        writer.write("\n\n")
        writer.write(textwrap.indent(body_block, I))

    return Stripped(writer.getvalue())


def _generate_write_to_stream(
    symbol_table: intermediate.SymbolTable,
    qualified_module_name: python_common.QualifiedModuleName,
) -> Stripped:
    """Generate the function to write an instance as XML to a stream."""
    docstring_blocks = [
        Stripped(
            """\
Write the XML representation of :paramref:`instance` to :paramref:`stream`."""
        )
    ]

    first_cls = (
        symbol_table.concrete_classes[0]
        if len(symbol_table.concrete_classes) > 0
        else None
    )

    if first_cls is not None:
        first_cls_name = python_naming.class_name(first_cls.name)

        docstring_blocks.append(
            Stripped(
                f"""\
Example usage:

.. code-block::

    import pathlib

    import {qualified_module_name}.types as aas_types
    import {qualified_module_name}.xmlization as aas_xmlization

    instance = {first_cls_name}(
       ... # some constructor arguments
    )

    pth = pathlib.Path(...)
    with pth.open("wt") as fid:
        aas_xmlization.write(instance, fid)"""
            )
        )

    docstring_blocks.append(
        Stripped(
            """\
:param instance: to be serialized
:param stream: to write to"""
        )
    )

    escaped_text = "\n\n".join(docstring_blocks).replace('"""', '\\"\\"\\"')
    docstring = Stripped(
        f"""\
\"\"\"
{escaped_text}
\"\"\""""
    )

    return Stripped(
        f"""\
def write(instance: aas_types.Class, stream: TextIO) -> None:
{I}{indent_but_first_line(docstring, I)}
{I}serializer = _Serializer(stream)
{I}serializer.visit(instance)"""
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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for XML de/serialization.

    The ``qualified_module_name`` indicates the fully-qualified name of the base module.
    """
    xml_namespace_literal = python_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    blocks = [
        _generate_module_docstring(
            symbol_table=symbol_table, qualified_module_name=qualified_module_name
        ),
        python_common.WARNING,
        # pylint: disable=line-too-long
        Stripped(
            f"""\
import base64
import io
import math
import os
import sys
from typing import (
{I}Any,
{I}Callable,
{I}Iterator,
{I}List,
{I}Mapping,
{I}Optional,
{I}Sequence,
{I}TextIO,
{I}Tuple,
{I}TypeVar,
{I}Union,
{I}TYPE_CHECKING
)
import xml.etree.ElementTree

if sys.version_info >= (3, 8):
{I}from typing import (
{II}Final,
{II}Protocol
{I})
else:
{I}from typing_extensions import (
{II}Final,
{II}Protocol
{I})

import {qualified_module_name}.stringification as aas_stringification
import {qualified_module_name}.types as aas_types

# See: https://stackoverflow.com/questions/55076778/why-isnt-this-function-type-annotated-correctly-error-missing-type-parameters
if TYPE_CHECKING:
    PathLike = os.PathLike[Any]
else:
    PathLike = os.PathLike"""
        ),
        Stripped(
            f"""\
#: XML namespace in which all the elements are expected to reside
NAMESPACE = {xml_namespace_literal}"""
        ),
        Stripped("# region De-serialization"),
        Stripped(
            """\
#: XML namespace as a prefix specially tailored for
#: :py:mod:`xml.etree.ElementTree`
_NAMESPACE_IN_CURLY_BRACKETS = f'{{{NAMESPACE}}}'"""
        ),
        Stripped(
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
        ),
        # pylint: disable=line-too-long
        Stripped(
            f"""\
class HasIterparse(Protocol):
{I}\"\"\"Parse an XML document incrementally.\"\"\"

{I}# NOTE (mristin, 2022-10-26):
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
            """\
Segment = Union[ElementSegment, IndexSegment]"""
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
def _with_elements_cleared_after_yield(
{II}iterator: Iterator[Tuple[str, Element]]
) -> Iterator[Tuple[str, Element]]:
{I}\"\"\"
{I}Map the :paramref:`iterator` such that the element is ``clear()``'ed
{I}*after* every ``yield``.

{I}:param iterator: to be mapped
{I}:yield: event and element from :paramref:`iterator`
{I}\"\"\"
{I}for event, element in iterator:
{II}yield event, element
{II}element.clear()"""
        ),
    ]  # type: List[Stripped]

    errors = []  # type: List[Error]

    # NOTE (mristin, 2022-10-08):
    # We generate first the public methods so that the reader can jump straight
    # to the most important part of the code.
    for cls in symbol_table.classes:
        blocks.append(
            _generate_read_cls_from_iterparse(
                cls=cls, qualified_module_name=qualified_module_name
            )
        )

        blocks.append(
            _generate_read_cls_from_stream(
                cls=cls, qualified_module_name=qualified_module_name
            )
        )

        blocks.append(
            _generate_read_cls_from_file(
                cls=cls, qualified_module_name=qualified_module_name
            )
        )

        blocks.append(
            _generate_read_cls_from_str(
                cls=cls, qualified_module_name=qualified_module_name
            )
        )

    blocks.extend(
        [
            _generate_read_from_iterparse(qualified_module_name=qualified_module_name),
            _generate_read_from_stream(qualified_module_name=qualified_module_name),
            _generate_read_from_file(qualified_module_name=qualified_module_name),
            _generate_read_from_str(qualified_module_name=qualified_module_name),
        ]
    )

    blocks.extend(
        [
            Stripped(
                """\
# NOTE (mristin, 2022-10-08):
# Directly using the iterator turned out to result in very complex function
# designs. The design became much simpler as soon as we considered one look-ahead
# element. We came up finally with the following pattern which all the protected
# reading functions below roughly follow:
#
# ..code-block::
#
#    _read_*(
#       look-ahead element,
#       iterator
#    ) -> result
#
# The reading functions all read from the ``iterator`` coming from
# :py:func:`xml.etree.ElementTree.iterparse` with the argument
# ``events=["start", "end"]``. The exception :py:class:`.DeserializationException`
# is raised in case of unexpected input.
#
# The reading functions are responsible to read the end element corresponding to the
# start look-ahead element.
#
# When it comes to error reporting, we use exceptions. The exceptions are raised in
# the *callee*, as usual. However, the context of the exception, such as the error path,
# is added in the *caller*, as only the caller knows the context of
# the lookahead-element. In particular, prepending the path segment corresponding to
# the lookahead-element is the responsibility of the *caller*, and not of
# the *callee*."""
            ),
            Stripped(
                f"""\
def _parse_element_tag(element: Element) -> str:
{I}\"\"\"
{I}Extract the tag name without the namespace prefix from :paramref:`element`.

{I}:param element: whose tag without namespace we want to extract
{I}:return: tag name without the namespace prefix
{I}:raise: :py:class:`DeserializationException` if unexpected :paramref:`element`
{I}\"\"\"
{I}if not element.tag.startswith(_NAMESPACE_IN_CURLY_BRACKETS):
{II}namespace, got_namespace, tag_wo_ns = (
{III}element.tag.rpartition('}}')
{II})
{II}if got_namespace:
{III}if namespace.startswith('{{'):
{IIII}namespace = namespace[1:]

{III}raise DeserializationException(
{IIII}f"Expected the element in the namespace {{NAMESPACE!r}}, "
{IIII}f"but got the element {{tag_wo_ns!r}} in the namespace {{namespace!r}}"
{III})
{II}else:
{III}raise DeserializationException(
{IIII}f"Expected the element in the namespace {{NAMESPACE!r}}, "
{IIII}f"but got the element {{tag_wo_ns!r}} without the namespace prefix"
{III})

{I}return element.tag[len(_NAMESPACE_IN_CURLY_BRACKETS):]"""
            ),
            Stripped(
                f"""\
def _raise_if_has_tail_or_attrib(
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
def _read_end_element(
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

{I}_raise_if_has_tail_or_attrib(next_element)

{I}return next_element"""
            ),
            Stripped('_ItemT = TypeVar("_ItemT")'),
            Stripped(
                f"""\
def _read_v_element(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}expected_tag: str,
{I}read_content: Callable[
{II}[Element, Iterator[Tuple[str, Element]]],
{II}_ItemT
{I}]
) -> _ItemT:
{I}\"\"\"
{I}Verify that :paramref:`element` bears the :paramref:`expected_tag`, and
{I}delegate the reading of its content to :paramref:`read_content`.

{I}This is used to read a single positional item wrapped in a named element,
{I}such as ``<v>`` for a list item, or ``<v1>``, ``<v2>``, *etc.* for
{I}a tuple item.

{I}:param element: look-ahead element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param expected_tag: expected tag of :paramref:`element`
{I}:param read_content: to read the content of :paramref:`element`
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}\"\"\"
{I}tag_wo_ns = _parse_element_tag(element)
{I}if tag_wo_ns != expected_tag:
{II}raise DeserializationException(
{III}f"Expected an element with the tag {{expected_tag!r}}, "
{III}f"but got an element with tag: {{tag_wo_ns!r}}"
{II})

{I}return read_content(element, iterator)"""
            ),
            Stripped(
                f"""\
def _read_list_of_items(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}read_item: Callable[
{II}[Element, Iterator[Tuple[str, Element]]],
{II}_ItemT
{I}]
) -> List[_ItemT]:
{I}\"\"\"
{I}Read a list of items from :paramref:`iterator`.

{I}:paramref:`read_item` is responsible for verifying the tag of each item
{I}element itself -- *e.g.*, by wrapping a scalar/enumeration reader with
{I}:py:func:`_read_v_element`, or by relying on a class's own dispatch by
{I}its natural element tag.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element enclosing the list
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param read_item: to read a single item, including its own end element
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed items
{I}\"\"\"
{I}if element.text is not None and len(element.text.strip()) != 0:
{II}raise DeserializationException(
{III}f"Expected only item elements and whitespace text, "
{III}f"but got text: {{element.text!r}}"
{II})

{I}result = []  # type: List[_ItemT]
{I}item_i = 0

{I}while True:
{II}next_event_element = next(iterator, None)
{II}if next_event_element is None:
{III}raise DeserializationException(
{IIII}"Expected one or more items from a list or the end element, "
{IIII}"but got end-of-input"
{III})

{II}next_event, next_element = next_event_element
{II}if next_event == 'end' and next_element.tag == element.tag:
{III}# We reached the end of the list.
{III}break

{II}if next_event != 'start':
{III}raise DeserializationException(
{IIII}"Expected a start element corresponding to an item, "
{IIII}f"but got event {{next_event!r}} and element {{next_element.tag!r}}"
{III})

{II}try:
{III}item = read_item(next_element, iterator)
{II}except DeserializationException as exception:
{III}exception.path._prepend(IndexSegment(next_element, item_i))
{III}raise

{II}result.append(item)
{II}item_i += 1

{I}return result"""
            ),
            Stripped(
                f"""\
def _read_text_from_element(
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
{I}_raise_if_has_tail_or_attrib(element)

{I}text = element.text

{I}end_element = _read_end_element(
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
                f"""\
_XS_BOOLEAN_LITERAL_SET = {{
{I}"1",
{I}"true",
{I}"0",
{I}"false",
}}"""
            ),
            Stripped(
                f"""\
def _read_bool_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> bool:
{I}\"\"\"
{I}Parse the text of :paramref:`element` as a boolean, and
{I}read the corresponding end element from :paramref:`iterator`.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}\"\"\"
{I}text = _read_text_from_element(
{II}element,
{II}iterator
{I})

{I}if text not in _XS_BOOLEAN_LITERAL_SET:
{II}raise DeserializationException(
{III}f"Expected a boolean, "
{III}f"but got an element with text: {{text!r}}"
{II})

{I}return text in ('1', 'true')"""
            ),
            Stripped(
                f"""\
def _read_int_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> int:
{I}\"\"\"
{I}Parse the text of :paramref:`element` as an integer, and
{I}read the corresponding end element from :paramref:`iterator`.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}\"\"\"
{I}text = _read_text_from_element(
{II}element,
{II}iterator
{I})

{I}try:
{II}value = int(text)
{I}except ValueError:
{II}# pylint: disable=raise-missing-from
{II}raise DeserializationException(
{III}f"Expected an integer, "
{III}f"but got an element with text: {{text!r}}"
{II})

{I}return value"""
            ),
            Stripped(
                f"""\
_TEXT_TO_XS_DOUBLE_LITERALS = {{
{I}"NaN": math.nan,
{I}"INF": math.inf,
{I}"-INF": -math.inf,
}}"""
            ),
            Stripped(
                f"""\
def _read_float_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> float:
{I}\"\"\"
{I}Parse the text of :paramref:`element` as a floating-point number, and
{I}read the corresponding end element from :paramref:`iterator`.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}\"\"\"
{I}text = _read_text_from_element(
{II}element,
{II}iterator
{I})

{I}value = _TEXT_TO_XS_DOUBLE_LITERALS.get(text, None)
{I}if value is None:
{II}try:
{III}value = float(text)
{II}except ValueError:
{III}# pylint: disable=raise-missing-from
{III}raise DeserializationException(
{IIII}f"Expected a floating-point number, "
{IIII}f"but got an element with text: {{text!r}}"
{III})

{I}return value"""
            ),
            Stripped(
                f"""\
def _read_str_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> str:
{I}\"\"\"
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
{I}\"\"\"
{I}# NOTE (mristin, 2022-10-26):
{I}# We do not use ``_read_text_from_element`` as that function expects
{I}# the ``element`` to contain *some* text. In contrast, this function
{I}# can also deal with empty text, in which case it returns an empty string.

{I}text = element.text

{I}end_element = _read_end_element(
{II}element,
{II}iterator
{I})

{I}if text is None:
{II}text = end_element.text

{I}_raise_if_has_tail_or_attrib(element)
{I}result = (
{II}text
{II}if text is not None
{II}else ""
{I})

{I}return result"""
            ),
            Stripped(
                f"""\
def _read_bytes_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> bytes:
{I}\"\"\"
{I}Parse the text of :paramref:`element` as base64-encoded bytes, and
{I}read the corresponding end element from :paramref:`iterator`.

{I}:param element: look-ahead element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed value
{I}\"\"\"
{I}text = _read_text_from_element(
{II}element,
{II}iterator
{I})

{I}try:
{II}value = base64.b64decode(text)
{I}except Exception:
{II}# pylint: disable=raise-missing-from
{II}raise DeserializationException(
{III}f"Expected a text as base64-encoded bytes, "
{III}f"but got an element with text: {{text!r}}"
{II})

{I}return value"""
            ),
        ]
    )

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        blocks.append(
            Stripped(
                "\n".join(
                    f'_TupleItem{i}T = TypeVar("_TupleItem{i}T")'
                    for i in range(1, max(tuple_arities) + 1)
                )
            )
        )
        for arity in tuple_arities:
            blocks.append(_generate_tuple_from_element(arity=arity))

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_read_enum_from_element_text(enumeration=our_type))
        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue
        elif isinstance(our_type, intermediate.AbstractClass):
            blocks.append(_generate_read_cls_as_element(cls=our_type))

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/read_{our_type.name}.py"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue
            else:
                blocks.extend(
                    [
                        _generate_reader_and_setter(cls=our_type),
                        _generate_read_as_sequence(cls=our_type),
                    ]
                )

                blocks.append(_generate_read_cls_as_element(cls=our_type))

        elif isinstance(our_type, intermediate.NamedUnion):
            blocks.append(_generate_read_named_union_as_element(named_union=our_type))

        else:
            assert_never(our_type)

    blocks.append(_generate_general_read_as_element(symbol_table=symbol_table))

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.AbstractClass):
            blocks.append(_generate_dispatch_map_for_class(cls=cls))
        elif isinstance(cls, intermediate.ConcreteClass):
            if len(cls.concrete_descendants) > 0:
                blocks.append(_generate_dispatch_map_for_class(cls=cls))

            if not cls.is_implementation_specific:
                blocks.append(_generate_reader_and_setter_map(cls=cls))

        else:
            assert_never(cls)

    for named_union in symbol_table.named_unions:
        blocks.append(_generate_dispatch_map_for_named_union(named_union=named_union))

    blocks.append(_generate_general_dispatch_map(symbol_table=symbol_table))

    blocks.append(Stripped("# endregion"))

    blocks.append(Stripped("# region Serialization"))

    blocks.append(_generate_serializer(symbol_table=symbol_table))

    blocks.append(
        _generate_write_to_stream(
            symbol_table=symbol_table, qualified_module_name=qualified_module_name
        )
    )

    blocks.append(
        Stripped(
            f"""\
def to_str(that: aas_types.Class) -> str:
{I}\"\"\"
{I}Serialize :paramref:`that` to an XML-encoded text.

{I}:param that: instance to be serialized
{I}:return: :paramref:`that` serialized to XML serialized to text
{I}\"\"\"
{I}writer = io.StringIO()
{I}write(that, writer)
{I}return writer.getvalue()"""
        )
    )

    blocks.append(Stripped("# endregion"))

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
