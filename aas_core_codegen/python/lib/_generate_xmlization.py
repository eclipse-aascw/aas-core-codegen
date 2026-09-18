"""Generate code for XML de/serialization."""

import io
import textwrap
from typing import (
    AbstractSet,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

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
    INDENT5 as IIIII,
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
to the stream.

The writing raises a :py:class:`SerializationException` if it can not serialize
the instance, be it because the stream failed or because a value could not be
written. The path of the exception points to the culprit as a Python access
expression, *e.g.*, ``.submodels[0].id``, so that you can find it in the instance
which you handed over."""
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
{I}return _read_enum_from_element_text(
{II}element,
{II}iterator,
{II}aas_stringification.{enum_from_str},
{II}{python_common.string_literal(enum_name)}
{I})"""
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
{I}return _read_instance_from_iterparse(
{II}iterator,
{II}{wrapped_function_name},
{II}{python_common.string_literal(cls_name)}
{I})"""
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

        expected_what = python_common.string_literal(
            f"a concrete instance of {cls_name!r}"
        )

        body = Stripped(
            f"""\
return _read_dispatched(
{I}element,
{I}iterator,
{I}{dispatch_map},
{I}{expected_what}
)"""
        )
    else:
        xml_cls_literal = python_common.string_literal(naming.xml_class_name(cls.name))

        read_as_sequence_function_name = python_naming.function_name(
            Identifier(f"_read_{cls.name}_as_sequence")
        )

        body = Stripped(
            f"""\
return _read_named_element(
{I}element,
{I}iterator,
{I}{xml_cls_literal},
{I}{read_as_sequence_function_name}
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
return _read_dispatched(
{I}element,
{I}iterator,
{I}{dispatch_map},
{I}{python_common.string_literal(f"a concrete instance of {union_name!r}")}
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
{I}return _read_instance_from_iterparse(
{II}iterator,
{II}_read_as_element,
{II}'an instance'
{I})"""
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
return _read_dispatched(
{I}element,
{I}iterator,
{I}{dispatch_map},
{I}'a concrete instance'
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
        f"read_item_{i}: _ContentReader[{type_var}]"
        for i, type_var in enumerate(type_vars, start=1)
    )

    param_docs = "\n".join(
        f"{I}:param read_item_{i}: "
        f"to read the item at the position {i - 1}, including its own end element"
        for i in range(1, arity + 1)
    )

    item_reads = "\n\n".join(
        f"""\
item_{i} = _read_tuple_item(
{I}element,
{I}iterator,
{I}{i - 1},
{I}read_item_{i}
)"""
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
{I}:py:func:`_read_named_element`, or by relying on a class's own dispatch by
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


def _is_encoded_as_text(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """
    Check whether a value of the ``type_annotation`` is encoded as an element's text.

    The primitives and the enumerations are; the instances are encoded as child
    elements instead.
    """
    if intermediate.try_primitive_type(type_annotation) is not None:
        return True

    return isinstance(type_annotation, intermediate.OurTypeAnnotation) and isinstance(
        type_annotation.our_type, intermediate.Enumeration
    )


def _content_reader_name(
    type_annotation: intermediate.TypeAnnotationUnion,
) -> Identifier:
    """
    Give out the name of the reader of the content of an element of
    the ``type_annotation``.

    The element has already been opened, and its tag was prescribed by whatever
    encloses it, so the tag says nothing about the value. An instance with concrete
    descendants is therefore nested in a discriminator element of its own.

    This is a pure function of the type annotation. The code of the readers which have
    to be composed is generated by :py:class:`_ReaderRegistry`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Identifier(_READ_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Expected to handle this case before")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return python_naming.private_function_name(
                Identifier(f"read_{our_type.name}_from_element_text")
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if len(our_type.concrete_descendants) > 0:
                return Identifier(
                    f"_read_nested__{python_common.atomic_moniker(type_anno)}"
                )

            return python_naming.private_function_name(
                Identifier(f"read_{our_type.name}_as_sequence")
            )

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # We keep this as its own branch, separate from the polymorphic-class case
            # above, even though the code is identical at the moment. We might want to
            # support unions of primitives in the future, at which point this branch
            # would need to diverge. Unlike a plain class, a named union always takes
            # the discriminator-nesting path, regardless of how many implementers it
            # flattens to.
            return Identifier(
                f"_read_nested__{python_common.atomic_moniker(type_anno)}"
            )

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        items_type_anno = intermediate.beneath_optional(type_anno.items)

        return Identifier(
            f"_read_list_of__{python_common.atomic_moniker(items_type_anno)}"
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        monikers = [python_common.atomic_moniker(item) for item in type_anno.items]

        return Identifier(
            f"_read_tuple{len(type_anno.items)}_of__" + "__".join(monikers)
        )

    else:
        assert_never(type_anno)


def _element_reader_name(
    type_annotation: intermediate.TypeAnnotationUnion, expected_tag: str
) -> Identifier:
    """
    Give out the name of the reader of a whole element of the ``type_annotation``,
    expected to be tagged ``expected_tag``.

    The wire format is asymmetric here. An instance element is self-describing -- its
    tag *is* its model type -- so it is read by dispatching on that tag, and
    the ``expected_tag`` plays no role. An element whose value is encoded as text is
    not self-describing: its tag gives only the position, ``v`` in a list and ``v1``,
    ``v2``, *etc.* in a tuple, so its reader has to check the tag which the enclosing
    element prescribes.

    This is a pure function of its arguments. The code of the readers which have to be
    composed is generated by :py:class:`_ReaderRegistry`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    if _is_encoded_as_text(type_anno):
        return Identifier(
            f"_read_{python_common.atomic_moniker(type_anno)}__at_{expected_tag}"
        )

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Expected an atomic type annotation, but got: {type_anno}"

    return python_naming.function_name(
        Identifier(f"_read_{type_anno.our_type.name}_as_element")
    )


class _ReaderRegistry:
    """
    Generate the code of the readers which a meta-model needs to be composed.

    All the readers share the same shape, ``(element, iterator) 🠒 value``: read the
    content of an element which has already been opened, including the corresponding
    end element. As the shape is uniform, a reader can be passed to another reader as
    its item reader, so that a list of tuples -- or anything deeper that a meta-model
    might grow -- falls out of the pieces which are already there instead of needing
    a helper generated for that particular combination.

    The composed readers are de-duplicated by the type which they read, so that all
    the classes share them, and they are named by :py:func:`_content_reader_name` and
    :py:func:`_element_reader_name`. Nothing is composed at the time of the reading:
    a reader is a module-level function, and the maps of the readers are built once,
    when the module is loaded.

    The methods come grouped: first the queries, which give out what has been
    registered so far and change nothing, and then the commands, which register and
    give out nothing.
    """

    def __init__(self) -> None:
        """Initialize with nothing registered."""
        self._blocks_by_name = dict()  # type: MutableMapping[Identifier, Stripped]
        self._needed_helpers = set()  # type: Set[str]

    @property
    def blocks(self) -> List[Stripped]:
        """Give out the code of the registered readers, ordered by the reader name."""
        return [self._blocks_by_name[name] for name in sorted(self._blocks_by_name)]

    @property
    def needed_helpers(self) -> AbstractSet[str]:
        """Give out the names of the shared helpers which the readers need."""
        return self._needed_helpers

    def note_needed_helper(self, name: str) -> None:
        """Note that the shared helper ``name`` is needed."""
        self._needed_helpers.add(name)

    def _add(self, name: Identifier, block: Stripped) -> None:
        """Register the ``block`` which defines the reader ``name``."""
        self._blocks_by_name[name] = block

    def _register_at_tag_reader(
        self, type_annotation: intermediate.TypeAnnotationUnion, expected_tag: str
    ) -> None:
        """Register the reader of a text-encoded value tagged ``expected_tag``."""
        self.note_needed_helper("_read_named_element")
        self.register_content_reader(type_annotation)

        name = _element_reader_name(type_annotation, expected_tag=expected_tag)

        value_type = python_common.generate_type(
            type_annotation, types_module=Identifier("aas_types")
        )

        content_reader = _content_reader_name(type_annotation)

        self._add(
            name,
            Stripped(
                f"""\
def {name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> {value_type}:
{I}\"\"\"
{I}Read the content of :paramref:`element`, which must be tagged
{I}``{expected_tag}``, as {python_common.describe_atomic_type(type_annotation)}.
{I}\"\"\"
{I}return _read_named_element(
{II}element,
{II}iterator,
{II}{python_common.string_literal(expected_tag)},
{II}{content_reader}
{I})"""
            ),
        )

    def _register_element_reader(
        self, type_annotation: intermediate.TypeAnnotationUnion, expected_tag: str
    ) -> None:
        """
        Register the readers needed to read a whole element of
        the ``type_annotation`` at the position tagged ``expected_tag``.
        """
        # NOTE (mristin):
        # An instance element is self-describing, so it is read by the function which
        # is generated together with the class, and there is nothing to register.
        if _is_encoded_as_text(type_annotation):
            self._register_at_tag_reader(type_annotation, expected_tag=expected_tag)

    def _register_list_reader(
        self, type_annotation: intermediate.ListTypeAnnotation
    ) -> None:
        """Register the reader of a list with the items of the ``type_annotation``."""
        self.note_needed_helper("_read_list_of_items")

        items_type_anno = intermediate.beneath_optional(type_annotation.items)

        if isinstance(
            items_type_anno,
            (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
        ):
            raise AssertionError(
                "(mristin) We handle only lists of primitive types and of our types "
                "in the XML de-serialization at the moment. The meta-model does not "
                "contain any other lists, so we wanted to keep the code as simple as "
                "possible, and avoid unrolling. Please contact the developers if you "
                "need this feature."
            )

        self._register_element_reader(items_type_anno, expected_tag="v")

        name = _content_reader_name(type_annotation)

        item_type = python_common.generate_type(
            items_type_anno, types_module=Identifier("aas_types")
        )

        read_item = _element_reader_name(items_type_anno, expected_tag="v")

        self._add(
            name,
            Stripped(
                f"""\
def {name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> List[{item_type}]:
{I}\"\"\"
{I}Read the items of :paramref:`element` as a list of
{I}{python_common.describe_atomic_type(items_type_anno)}.
{I}\"\"\"
{I}return _read_list_of_items(
{II}element,
{II}iterator,
{II}{read_item}
{I})"""
            ),
        )

    def _register_tuple_reader(
        self, type_annotation: intermediate.TupleTypeAnnotation
    ) -> None:
        """Register the reader of a tuple with the items of the ``type_annotation``."""
        arity = len(type_annotation.items)

        self.note_needed_helper("_read_tuple_item")

        read_items = []  # type: List[Identifier]
        item_types = []  # type: List[Stripped]

        for i, item_type_anno in enumerate(type_annotation.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, constrained "
                "primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so "
                "no nested optionals, lists or tuples are expected here."
            )

            expected_tag = f"v{i + 1}"

            self._register_element_reader(item_type_anno, expected_tag=expected_tag)

            read_items.append(
                _element_reader_name(item_type_anno, expected_tag=expected_tag)
            )
            item_types.append(
                python_common.generate_type(
                    item_type_anno, types_module=Identifier("aas_types")
                )
            )

        name = _content_reader_name(type_annotation)

        tuple_type = "Tuple[" + ", ".join(item_types) + "]"
        if len(tuple_type) > 88:
            joined_item_types = ",\n".join(item_types)
            tuple_type = f"""\
Tuple[
{I}{indent_but_first_line(joined_item_types, I)}
]"""

        joined_read_items = ",\n".join(read_items)

        self._add(
            name,
            Stripped(
                f"""\
def {name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> {tuple_type}:
{I}\"\"\"
{I}Read the items of :paramref:`element` as a tuple of {arity} item(s).
{I}\"\"\"
{I}return _tuple{arity}_from_element(
{II}element,
{II}iterator,
{II}{indent_but_first_line(joined_read_items, II)}
{I})"""
            ),
        )

    def _register_nested_reader(
        self, type_annotation: intermediate.OurTypeAnnotation
    ) -> None:
        """Register the reader of an instance nested in a discriminator element."""
        self.note_needed_helper("_read_nested_element")

        our_type = type_annotation.our_type

        name = _content_reader_name(type_annotation)

        value_type = python_common.generate_type(
            type_annotation, types_module=Identifier("aas_types")
        )

        read_as_element = python_naming.function_name(
            Identifier(f"_read_{our_type.name}_as_element")
        )

        type_name = (
            python_naming.union_name(our_type.name)
            if isinstance(our_type, intermediate.NamedUnion)
            else python_naming.class_name(our_type.name)
        )

        self._add(
            name,
            Stripped(
                f"""\
def {name}(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]]
) -> {value_type}:
{I}\"\"\"
{I}Read an instance of :py:class:`.types.{type_name}` nested in
{I}:paramref:`element` as a discriminator element.
{I}\"\"\"
{I}return _read_nested_element(
{II}element,
{II}iterator,
{II}{read_as_element},
{II}{python_common.string_literal(type_name)}
{I})"""
            ),
        )

    def register_content_reader(
        self, type_annotation: intermediate.TypeAnnotationUnion
    ) -> None:
        """
        Register the readers, and note the shared helpers, needed to read the content
        of an element of the ``type_annotation``.
        """
        type_anno = intermediate.beneath_optional(type_annotation)

        primitive_type = intermediate.try_primitive_type(type_anno)
        if primitive_type is not None:
            self.note_needed_helper(_READ_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])
            return

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type

            if isinstance(our_type, intermediate.Enumeration):
                self.note_needed_helper("_read_enum_from_element_text")

                # NOTE (mristin):
                # The reader of an enumeration is generated in the loop over our types,
                # so we only note here that the meta-model reaches it.
                self.note_needed_helper(_content_reader_name(type_anno))

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected to handle this case before")

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                # NOTE (mristin):
                # A class without concrete descendants is read by the function which is
                # generated together with the class, so there is nothing to register.
                if len(our_type.concrete_descendants) > 0:
                    self._register_nested_reader(type_anno)

            elif isinstance(our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # See the note in :py:func:`_content_reader_name` on why a named union
                # is kept in a branch of its own.
                self._register_nested_reader(type_anno)

            else:
                assert_never(our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            self._register_list_reader(type_anno)

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            self._register_tuple_reader(type_anno)

        else:
            assert_never(type_anno)


def _generate_readers_map(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the mapping XML property name 🠒 reader of the property's content."""
    cls_name = python_naming.class_name(cls.name)

    mapping_name = python_naming.private_constant_name(
        Identifier(f"readers_for_{cls.name}")
    )

    writer = io.StringIO()
    writer.write(
        f"""\
#: Read the content of a property of
#: :py:class:`.types.{cls_name}`, by the XML name of the property
{mapping_name}: Mapping[
{I}str,
{I}_ContentReader[Any]
] = {{
"""
    )

    for prop in cls.properties:
        reader = _content_reader_name(prop.type_annotation)

        writer.write(f"{I}{python_common.string_literal(prop.xml_name)}: {reader},\n")

    writer.write("}")

    return Stripped(writer.getvalue())


def _generate_read_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the function to read the instance as sequence of XML-encoded properties.

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

    cls_name = python_naming.class_name(cls.name)

    readers_map_name = python_naming.private_constant_name(
        Identifier(f"readers_for_{cls.name}")
    )

    blocks = []  # type: List[Stripped]

    if len(cls.properties) == 0:
        blocks.append(
            Stripped(
                f"""\
_read_properties(
{I}element,
{I}iterator,
{I}{readers_map_name}
)"""
            )
        )

        blocks.append(Stripped(f"return aas_types.{cls_name}()"))
    else:
        blocks.append(
            Stripped(
                f"""\
values = _read_properties(
{I}element,
{I}iterator,
{I}{readers_map_name}
)"""
            )
        )

        # region Pick the values out, so that the constructor call is type-checked

        variable_by_prop_name = dict()  # type: MutableMapping[Identifier, Identifier]

        extractions = []  # type: List[Stripped]
        for prop in cls.properties:
            variable = python_naming.variable_name(Identifier(f"the_{prop.name}"))
            variable_by_prop_name[prop.name] = variable

            prop_type = python_common.generate_type(
                prop.type_annotation, types_module=Identifier("aas_types")
            )

            # NOTE (mristin):
            # A property is unset until we read it, so all the variables are optional
            # regardless of whether the property itself is.
            if not isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ):
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

            xml_name_literal = python_common.string_literal(prop.xml_name)

            one_liner = f"{variable}: {prop_type} = values.get({xml_name_literal})"

            # NOTE (mristin):
            # We break the extraction over multiple lines only if it does not fit
            # on a single line, as most of the extractions comfortably do.
            if "\n" not in one_liner and len(one_liner) <= 88:
                extractions.append(Stripped(one_liner))
            else:
                extractions.append(
                    Stripped(
                        f"""\
{variable}: {prop_type} = values.get(
{I}{xml_name_literal}
)"""
                    )
                )

        blocks.append(Stripped("\n".join(extractions)))

        # endregion

        for prop in cls.properties:
            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                continue

            cause_literal = python_common.string_literal(
                f"The required property {prop.xml_name!r} is missing"
            )

            blocks.append(
                Stripped(
                    f"""\
if {variable_by_prop_name[prop.name]} is None:
{I}raise DeserializationException(
{II}{cause_literal}
{I})"""
                )
            )

        init_writer = io.StringIO()
        init_writer.write(f"return aas_types.{cls_name}(\n")

        for i, arg in enumerate(cls.constructor.arguments):
            init_writer.write(f"{I}{variable_by_prop_name[arg.name]}")

            if i < len(cls.constructor.arguments) - 1:
                init_writer.write(",\n")
            else:
                init_writer.write("\n")

        init_writer.write(")")

        blocks.append(Stripped(init_writer.getvalue()))

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

    # NOTE (mristin):
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


_WRITE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "_write_bool_as_element",
    intermediate.PrimitiveType.INT: "_write_int_as_element",
    intermediate.PrimitiveType.FLOAT: "_write_float_as_element",
    intermediate.PrimitiveType.STR: "_write_str_as_element",
    intermediate.PrimitiveType.BYTEARRAY: "_write_bytes_as_element",
}
assert all(
    literal in _WRITE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _count_required_properties(cls: intermediate.Class) -> int:
    """Count the number of properties which are marked as non-optional."""
    return sum(
        1
        for prop in cls.properties
        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
    )


def _collapses_to_empty_element(cls: intermediate.ConcreteClass) -> bool:
    """
    Check whether the element enclosing an instance of the ``cls`` can be empty.

    If none of the properties is required, an instance with nothing set writes no
    content at all, and we collapse the enclosing element to ``<name/>`` instead of
    writing ``<name></name>``.
    """
    return _count_required_properties(cls) == 0


#: Maximum length of a line of the generated code, in columns
_MAX_LINE_LENGTH = 88


def _join_arguments(
    function: Identifier, arguments: Sequence[str], columns: int
) -> Stripped:
    """
    Render the call to the ``function`` with the ``arguments``.

    The rendered call is expected to be finally indented by ``columns`` columns. The
    arguments go on the same line as the ``function`` if the call fits in
    :py:attr:`_MAX_LINE_LENGTH` columns, on a single continuation line if *that* fits,
    and one argument per line otherwise.
    """
    joined = ", ".join(arguments)

    if columns + len(function) + len("(") + len(joined) + len(")") <= _MAX_LINE_LENGTH:
        return Stripped(f"{function}({joined})")

    if columns + len(I) + len(joined) <= _MAX_LINE_LENGTH:
        return Stripped(
            f"""\
{function}(
{I}{joined}
)"""
        )

    arguments_joined = ",\n".join(f"{I}{argument}" for argument in arguments)
    return Stripped(
        f"""\
{function}(
{arguments_joined}
)"""
    )


def _cls_element_writer_name(cls: intermediate.ConcreteClass) -> Identifier:
    """Give out the name of the writer of an instance of the ``cls`` as an element."""
    return python_naming.private_function_name(
        Identifier(f"write_{cls.name}_as_element")
    )


def _cls_sequence_writer_name(cls: intermediate.ConcreteClass) -> Identifier:
    """
    Give out the name of the writer of the properties of the ``cls`` as a sequence.

    Only an implementation-specific class has such a writer, and it comes from
    a snippet. Every other class writes its properties directly in its element
    writer, see :py:func:`_cls_element_writer_name`, since nothing else would call
    the sequence.
    """
    return python_naming.private_function_name(
        Identifier(f"write_{cls.name}_as_sequence")
    )


def _tuple_writer_name(type_annotation: intermediate.TupleTypeAnnotation) -> Identifier:
    """Give out the name of the writer of a tuple of the ``type_annotation``."""
    monikers = [python_common.atomic_moniker(item) for item in type_annotation.items]

    return Identifier(
        f"_write_tuple{len(type_annotation.items)}_of__" + "__".join(monikers)
    )


def _element_writer_call(
    type_annotation: intermediate.TypeAnnotationUnion,
    prop_name: Optional[str],
    value: str,
) -> Tuple[Identifier, List[str]]:
    """
    Give out the function, and the arguments which follow the element name, writing
    the ``value`` of the ``type_annotation`` as a whole XML element.

    Every writer shares the shape ``(name, prop_name, value, serializer) 🠒 None``: it
    writes the element tag as well, since the tag either comes from the position of
    the value -- the XML name of a property, or ``v``/``v1``, ``v2``, *etc.* -- or
    from the run-time type of the value. A writer therefore owns its element, which
    is what lets it collapse the element to ``<name/>``: an empty list and an instance
    with nothing set do so.

    The ``prop_name`` is the name of the property, as spelled in Python, whose value
    is written. The writer attributes a failure to it, see
    :py:func:`_generate_attribute_to_property`, so that the path to the culprit falls
    out as the stack unwinds. It is ``None`` when the access which leads to the value
    is recorded by an enclosing writer instead -- an item of a collection is recorded
    by its index, for example -- so that no segment of the path is written twice.

    This is a pure function of its arguments. The code of the writers which have to be
    composed is generated by :py:class:`_WriterRegistry`.
    """
    type_anno = intermediate.beneath_optional(type_annotation)

    prop_literal = (
        python_common.string_literal(prop_name) if prop_name is not None else "None"
    )

    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return (
            Identifier(_WRITE_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type]),
            [prop_literal, value, "serializer"],
        )

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Expected to handle this case before")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        if isinstance(our_type, intermediate.Enumeration):
            # NOTE (mristin):
            # The literal is written as the text of the element, and one shared
            # writer serves every enumeration. We deliberately do *not* spell out
            # the access to the literal's value here: a value which is not a literal
            # of the enumeration would then break *before* the writer is entered,
            # and the failure could no longer be attributed to the property.
            return (
                Identifier("_write_enum_as_element"),
                [prop_literal, value, "serializer"],
            )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if len(our_type.concrete_descendants) > 0:
                return (
                    Identifier("_write_nested_element"),
                    [prop_literal, value, "serializer"],
                )

            assert isinstance(our_type, intermediate.ConcreteClass), (
                f"Unexpected abstract class with no concrete "
                f"descendants: {our_type.name!r}"
            )

            return (
                _cls_element_writer_name(our_type),
                [prop_literal, value, "serializer"],
            )

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # We keep this as its own branch, separate from the polymorphic-class case
            # above, even though the code is identical at the moment. We might want to
            # support unions of primitives in the future, at which point this branch
            # would need to diverge. Unlike a plain class, a named union always takes
            # the discriminator-nesting path, regardless of how many implementers it
            # flattens to.
            return (
                Identifier("_write_nested_element"),
                [prop_literal, value, "serializer"],
            )

        else:
            assert_never(our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        items_type_anno = intermediate.beneath_optional(type_anno.items)

        if not _is_encoded_as_text(items_type_anno):
            return (
                Identifier("_write_list_of_instances"),
                [prop_literal, value, "serializer"],
            )

        items_primitive_type = intermediate.try_primitive_type(items_type_anno)
        if items_primitive_type is not None:
            write_item = Identifier(
                _WRITE_FUNCTION_BY_PRIMITIVE_TYPE[items_primitive_type]
            )
        else:
            assert isinstance(items_type_anno, intermediate.OurTypeAnnotation)
            assert isinstance(items_type_anno.our_type, intermediate.Enumeration)

            write_item = Identifier("_write_enum_as_element")

        return (
            Identifier("_write_list_of_items"),
            [prop_literal, value, write_item, "serializer"],
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return (_tuple_writer_name(type_anno), [prop_literal, value, "serializer"])

    else:
        assert_never(type_anno)

    raise AssertionError("Should not have gotten here")


class _WriterRegistry:
    """
    Generate the code of the writers which a meta-model needs to be composed.

    This is the write-side dual of :py:class:`_ReaderRegistry`. All the writers share
    the same shape, ``(name, value, serializer) 🠒 None``: write the ``value`` as
    a whole XML element tagged ``name``, the tag included. As the shape is uniform,
    a writer can be given to another writer as its item writer, so that a list of
    enumeration literals -- or anything deeper that a meta-model might grow -- falls
    out of the pieces which are already there.

    The composed writers are de-duplicated by the type which they write, so that all
    the classes share them, and they are named by :py:func:`_element_writer_call`.
    Nothing is composed at the time of the writing: a writer is a module-level
    function, so the serialization allocates neither a closure nor a bound method.

    The methods come grouped: first the queries, which give out what has been
    registered so far and change nothing, and then the commands, which register and
    give out nothing.
    """

    def __init__(self) -> None:
        """Initialize with nothing registered."""
        self._blocks_by_name = dict()  # type: MutableMapping[Identifier, Stripped]
        self._needed_helpers = set()  # type: Set[str]

    @property
    def blocks(self) -> List[Stripped]:
        """Give out the code of the registered writers, ordered by the writer name."""
        return [self._blocks_by_name[name] for name in sorted(self._blocks_by_name)]

    @property
    def needed_helpers(self) -> AbstractSet[str]:
        """Give out the names of the shared helpers which the writers need."""
        return self._needed_helpers

    def note_needed_helper(self, name: str) -> None:
        """Note that the shared helper ``name`` is needed."""
        self._needed_helpers.add(name)

    def _add(self, name: Identifier, block: Stripped) -> None:
        """Register the ``block`` which defines the writer ``name``."""
        self._blocks_by_name[name] = block

    def _register_tuple_writer(
        self, type_annotation: intermediate.TupleTypeAnnotation
    ) -> None:
        """Register the writer of a tuple with the items of the ``type_annotation``."""
        arity = len(type_annotation.items)

        name = _tuple_writer_name(type_annotation)

        value_type = python_common.generate_type(
            type_annotation, types_module=Identifier("aas_types")
        )

        statements = []  # type: List[Stripped]

        for i, item_type_anno in enumerate(type_annotation.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, constrained "
                "primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so "
                "no nested optionals, lists or tuples are expected here."
            )

            item_value = f"value[{i}]"

            write: Stripped

            # NOTE (mristin):
            # An instance is self-describing -- the element tag *is* its model type --
            # so it writes its own element and the positional tag plays no role. Only
            # a value encoded as text needs the tag which its position prescribes.
            if not _is_encoded_as_text(item_type_anno):
                write = Stripped(f"serializer.visit({item_value})")
            else:
                self.register_property_writer(item_type_anno)

                function, arguments = _element_writer_call(
                    item_type_anno, None, item_value
                )

                write = _join_arguments(
                    function,
                    [python_common.string_literal(f"v{i + 1}")] + arguments,
                    columns=len(III),
                )

            # NOTE (mristin):
            # An item is selected by its position in the tuple, so the failure is
            # attributed to the index, and the item's own element contributes
            # no segment to the path.
            statements.append(
                Stripped(
                    f"""\
try:
{I}{indent_but_first_line(write, I)}
except Exception as exception:
{I}_attribute_to_item(exception, {i})"""
                )
            )

        statements_joined = "\n\n".join(statements)

        self._add(
            name,
            Stripped(
                f"""\
def {name}(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: {indent_but_first_line(value_type, I)},
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the {arity} item(s) of :paramref:`value` enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the enclosing element
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)

{II}{indent_but_first_line(statements_joined, II)}

{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
            ),
        )

    def register_property_writer(
        self, type_annotation: intermediate.TypeAnnotationUnion
    ) -> None:
        """
        Register the writers, and note the shared helpers, needed to write a value of
        the ``type_annotation`` as a whole XML element.
        """
        type_anno = intermediate.beneath_optional(type_annotation)

        primitive_type = intermediate.try_primitive_type(type_anno)
        if primitive_type is not None:
            self.note_needed_helper(_WRITE_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])
            return

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            raise AssertionError("Expected to handle this case before")

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type

            if isinstance(our_type, intermediate.Enumeration):
                self.note_needed_helper("_write_enum_as_element")

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Expected to handle this case before")

            elif isinstance(
                our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
            ):
                # NOTE (mristin):
                # A class without concrete descendants is written by the function which
                # is generated together with the class, so there is nothing to register.
                if len(our_type.concrete_descendants) > 0:
                    self.note_needed_helper("_write_nested_element")

            elif isinstance(our_type, intermediate.NamedUnion):
                # NOTE (mristin):
                # See the note in :py:func:`_element_writer_call` on why a named union
                # is kept in a branch of its own.
                self.note_needed_helper("_write_nested_element")

            else:
                assert_never(our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            items_type_anno = intermediate.beneath_optional(type_anno.items)

            if isinstance(
                items_type_anno,
                (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
            ):
                raise AssertionError(
                    "(mristin) We handle only lists of primitive types and of our types "
                    "in the XML serialization at the moment. The meta-model does not "
                    "contain any other lists, so we wanted to keep the code as simple "
                    "as possible, and avoid unrolling. Please contact the developers "
                    "if you need this feature."
                )

            if not _is_encoded_as_text(items_type_anno):
                self.note_needed_helper("_write_list_of_instances")
                return

            self.note_needed_helper("_write_list_of_items")

            self.register_property_writer(items_type_anno)

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            self._register_tuple_writer(type_anno)

        else:
            assert_never(type_anno)


def _generate_write_property(prop: intermediate.Property) -> Stripped:
    """Generate the statement which writes the property ``prop`` of ``that``."""
    prop_name = python_naming.property_name(prop.name)
    xml_prop_literal = python_common.string_literal(prop.xml_name)

    optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

    function, arguments = _element_writer_call(
        prop.type_annotation, prop_name, f"that.{prop_name}"
    )

    # NOTE (mristin):
    # The properties are written in the body of the element writer, which wraps them
    # in a ``try``, so they sit one level deeper than the body of the function.
    call = _join_arguments(
        function,
        [xml_prop_literal] + arguments,
        columns=len(III) if optional else len(II),
    )

    if not optional:
        return call

    return Stripped(
        f"""\
if that.{prop_name} is not None:
{I}{indent_but_first_line(call, I)}"""
    )


def _generate_write_cls_as_element(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the function to write an instance of the ``cls`` as an XML element.

    The element tag comes from the caller, as it depends on where the instance sits:
    it is the XML name of the class when the instance is visited, and the XML name of
    a property when the instance is the value of that property. The writer owning its
    element is what lets it collapse to ``<name/>``, see
    :py:func:`_collapses_to_empty_element`.

    The properties are written directly in the body, since nothing else would call
    a writer of the sequence. An implementation-specific class is the exception: its
    content comes from a snippet, so the generated writer only frames the element
    around it, just as the reading side frames the dispatch around the snippet.
    """
    cls_name = python_naming.class_name(cls.name)
    function_name = _cls_element_writer_name(cls)

    body_blocks = []  # type: List[Stripped]
    docstring_blocks = [
        Stripped(
            """\
Write :paramref:`that` enclosed in the :paramref:`name` element."""
        )
    ]

    if cls.is_implementation_specific:
        docstring_blocks.append(
            Stripped(
                f"""\
The content is written by :py:func:`{_cls_sequence_writer_name(cls)}`, which comes
from an implementation-specific snippet. The element is therefore never collapsed
to an empty one: what an instance of this class writes does not follow from its
properties, so we can not tell in advance that it writes nothing.

For the same reason, a failure in the snippet is attributed to :paramref:`that`
as a whole, and not to one of its properties."""
            )
        )

        body_blocks.append(
            Stripped(
                f"""\
serializer._write_start_element(name)
{_cls_sequence_writer_name(cls)}(that, serializer)
serializer._write_end_element(name)"""
            )
        )
    elif len(cls.properties) == 0:
        docstring_blocks.append(
            Stripped(
                """\
There are no properties specified for this class, so the element is always
empty."""
            )
        )

        body_blocks.append(Stripped("serializer._write_empty_element(name)"))
    else:
        if _collapses_to_empty_element(cls):
            docstring_blocks.append(
                Stripped(
                    """\
All the properties are optional, so the element is collapsed to an empty one
if none of them is set."""
                )
            )

            conjunction = "\n".join(
                (
                    f"that.{python_naming.property_name(prop.name)} is None"
                    if i == 0
                    else f"and that.{python_naming.property_name(prop.name)} is None"
                )
                for i, prop in enumerate(cls.properties)
            )

            body_blocks.append(
                Stripped(
                    f"""\
# We optimize for the case where all the optional properties are not set,
# so that we can simply output an empty element.
if (
{II}{indent_but_first_line(conjunction, II)}
):
{I}serializer._write_empty_element(name)
{I}return"""
                )
            )

        property_blocks = [
            _generate_write_property(prop=prop) for prop in cls.properties
        ]

        property_blocks_joined = "\n".join(property_blocks)

        body_blocks.append(
            Stripped(
                f"""\
serializer._write_start_element(name)
{property_blocks_joined}
serializer._write_end_element(name)"""
            )
        )

    docstring_blocks.append(
        Stripped(
            f"""\
:param name: of the element tag. Expected to contain no XML special characters.
:param prop_name:
{I}name of the property, as spelled in Python, whose value is written, or
{I}``None`` if the access to the value is recorded by an enclosing writer
:param that: instance to be serialized
:param serializer: to write to
:raise: :py:class:`SerializationException` if the value could not be written"""
        )
    )

    escaped_text = "\n\n".join(docstring_blocks).replace('"""', '\\"\\"\\"')
    docstring = Stripped(
        f"""\
\"\"\"
{escaped_text}
\"\"\""""
    )

    body_blocks_joined = "\n\n".join(body_blocks)

    return Stripped(
        f"""\
def {function_name}(
{I}name: str,
{I}prop_name: Optional[str],
{I}that: aas_types.{cls_name},
{I}serializer: '_Serializer'
) -> None:
{I}{indent_but_first_line(docstring, I)}
{I}try:
{II}{indent_but_first_line(body_blocks_joined, II)}
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
    )


def _generate_visit_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """
    Generate the method to serialize the ``cls`` as an XML element.

    The generated method lives in the ``_Serializer`` class, and only gives the XML
    name of the class as the element tag to the writer of the class.
    """
    cls_name = python_naming.class_name(cls.name)
    visit_name = python_naming.method_name(Identifier(f"visit_{cls.name}"))
    xml_cls_literal = python_common.string_literal(naming.xml_class_name(cls.name))

    call = _join_arguments(
        _cls_element_writer_name(cls),
        [xml_cls_literal, "None", "that", "self"],
        columns=len(II),
    )

    return Stripped(
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
{I}{indent_but_first_line(call, I)}"""
    )


# fmt: off
@require(
    lambda symbol_table:
    '"' not in symbol_table.meta_model.xml_namespace,
    "No single quotes expected in the XML namespace so that we can directly "
    "write the namespace as-is"
)
# fmt: on
def _generate_serializer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """
    Generate the serializer as a visitor which writes to a stream on visits.

    The serializer carries the state of the writing -- the stream and whether the XML
    namespace still has to be specified -- and dispatches an instance to its writer.
    Everything else is a module-level function which is given the serializer, so that
    the writers can be composed without allocating a closure or a bound method.
    """
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
# NOTE (mristin):
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

{I}# NOTE (mristin):
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
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
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
            f"""\
:param instance: to be serialized
:param stream: to write to
:raise:
{I}:py:class:`SerializationException` if :paramref:`instance` could not be
{I}serialized"""
        )
    )

    escaped_text = "\n\n".join(docstring_blocks).replace('"""', '\\"\\"\\"')
    docstring = Stripped(
        f"""\
\"\"\"
{escaped_text}
\"\"\""""
    )

    # NOTE (mristin):
    # An instance which is not a class of the meta-model breaks on the dispatch, so
    # the failure comes from *outside* any of the writers, and has to be funnelled
    # here. Everything below is already funnelled by the writer which it broke in.
    return Stripped(
        f"""\
def write(instance: aas_types.Class, stream: TextIO) -> None:
{I}{indent_but_first_line(docstring, I)}
{I}serializer = _Serializer(stream)

{I}try:
{II}serializer.visit(instance)
{I}except Exception as exception:
{II}_attribute_to_property(exception, None)"""
    )


_READING_PATTERN_NOTE = Stripped(
    """\
# NOTE (mristin):
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
)


#: Note the shared reading helpers which a helper itself needs, so that we can
#: generate only the helpers which a meta-model actually reaches
#: Shared helpers which a helper needs, by the name of the helper. Both
#: the de-serialization and the serialization are covered, as they are gated
#: the same way, see :py:func:`_collect_needed_helpers`.
_HELPER_DEPENDENCIES = {
    "_parse_element_tag": [],
    "_raise_if_has_tail_or_attrib": [],
    "_read_end_element": ["_raise_if_has_tail_or_attrib"],
    "_read_named_element": ["_parse_element_tag"],
    "_read_nested_element": ["_read_end_element"],
    "_read_dispatched": ["_parse_element_tag"],
    "_read_properties": ["_parse_element_tag", "_raise_if_has_tail_or_attrib"],
    "_read_list_of_items": [],
    "_read_tuple_item": [],
    "_read_instance_from_iterparse": [],
    "_read_text_from_element": ["_raise_if_has_tail_or_attrib", "_read_end_element"],
    "_collapse_whitespace": [],
    "_read_bool_from_element_text": [
        "_read_text_from_element",
        "_collapse_whitespace",
    ],
    "_read_int_from_element_text": [
        "_read_text_from_element",
        "_collapse_whitespace",
    ],
    "_read_float_from_element_text": [
        "_read_text_from_element",
        "_collapse_whitespace",
    ],
    "_read_str_from_element_text": [
        "_read_end_element",
        "_raise_if_has_tail_or_attrib",
    ],
    "_read_bytes_from_element_text": ["_read_text_from_element"],
    "_read_enum_from_element_text": ["_read_text_from_element"],
    "_write_nested_element": [],
    "_write_list_of_instances": [],
    "_write_list_of_items": [],
    "_write_enum_as_element": ["_write_str_as_element"],
    "_write_bool_as_element": [],
    "_write_int_as_element": [],
    "_write_float_as_element": [],
    "_write_str_as_element": [],
    "_write_bytes_as_element": [],
}  # type: Mapping[str, Sequence[str]]


def _generate_reading_helpers() -> Mapping[str, Stripped]:
    """
    Generate the code of the shared reading helpers, by the name of the helper.

    Only the helpers which a meta-model reaches are finally generated, see
    :py:func:`_collect_needed_helpers`, so that a small meta-model does not pay for
    the readers which it never calls.
    """
    return {
        "_parse_element_tag": Stripped(
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
        "_raise_if_has_tail_or_attrib": Stripped(
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
        "_read_end_element": Stripped(
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
        "_read_named_element": Stripped(
            f"""\
def _read_named_element(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}expected_tag: str,
{I}read_content: _ContentReader[_ValueT]
) -> _ValueT:
{I}\"\"\"
{I}Verify that :paramref:`element` bears the :paramref:`expected_tag`, and
{I}delegate the reading of its content to :paramref:`read_content`.

{I}This is the only place where an element's tag is checked against the tag which
{I}its container prescribes -- the XML name of a class, ``<v>`` for a list item, or
{I}``<v1>``, ``<v2>``, *etc.* for a tuple item.

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
        "_read_nested_element": Stripped(
            f"""\
def _read_nested_element(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}read_element: _ContentReader[_ValueT],
{I}expected_what: str
) -> _ValueT:
{I}\"\"\"
{I}Read the instance nested in :paramref:`element` as a discriminator element.

{I}This looks redundant next to reading a list item, and it is not. A property
{I}wraps its instance in an element of its own, so the discriminator's name has to
{I}be prepended to the error path, which then reads ``value/property/idShort``.
{I}A list item is not wrapped -- the item element *is* the indexed child -- so the
{I}same prepend would give ``annotations/*[0]/property/idShort``, which walks one
{I}level past the element that ``*[0]`` already selects, and resolves to nothing.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element enclosing the discriminator element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param read_element: to read the nested element, dispatching on its tag
{I}:param expected_what: name of the expected type, for the error messages
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}f"Expected a discriminator start element corresponding "
{III}f"to {{expected_what}}, but got end-of-input"
{II})

{I}next_event, nested_element = next_event_element
{I}if next_event != 'start':
{II}raise DeserializationException(
{III}f"Expected a discriminator start element corresponding "
{III}f"to {{expected_what}}, "
{III}f"but got event {{next_event!r}} and element {{nested_element.tag!r}}"
{II})

{I}try:
{II}result = read_element(nested_element, iterator)
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(nested_element))
{II}raise

{I}_read_end_element(element, iterator)

{I}return result"""
        ),
        "_read_dispatched": Stripped(
            f"""\
def _read_dispatched(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}dispatch: Mapping[str, _ContentReader[_ValueT]],
{I}expected_what: str
) -> _ValueT:
{I}\"\"\"
{I}Read the instance of :paramref:`element` by dispatching on its own tag.

{I}An instance element is self-describing: its tag *is* its model type.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}:param element: start element of the instance
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param dispatch: to read the instance as a sequence, by its model type
{I}:param expected_what: what we expected to read, for the error messages
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
{I}tag_wo_ns = _parse_element_tag(element)

{I}read_as_sequence = dispatch.get(tag_wo_ns, None)
{I}if read_as_sequence is None:
{II}raise DeserializationException(
{III}f"Expected the element tag to be a valid model type "
{III}f"of {{expected_what}}, "
{III}f"but got tag {{tag_wo_ns!r}}"
{II})

{I}return read_as_sequence(element, iterator)"""
        ),
        "_read_properties": Stripped(
            f"""\
def _read_properties(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}readers: Mapping[str, _ContentReader[Any]]
) -> Mapping[str, Any]:
{I}\"\"\"
{I}Read the properties of an instance as the children of :paramref:`element`.

{I}The end element corresponding to :paramref:`element` will be read as well.

{I}The property is marked on the error path here, once for all the properties,
{I}instead of in every reader: the tag of the child element *is* the XML name of
{I}the property which we are reading.

{I}:param element: start element, parent of the properties
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param readers: to read the content of a property, by its XML name
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed values, by the XML name of the property
{I}\"\"\"
{I}if element.text is not None and len(element.text.strip()) != 0:
{II}raise DeserializationException(
{III}f"Expected only XML elements representing the properties "
{III}f"and whitespace text, but got text: {{element.text!r}}"
{II})

{I}_raise_if_has_tail_or_attrib(element)

{I}values = dict()  # type: Dict[str, Any]

{I}while True:
{II}# NOTE (mristin):
{II}# We pull the next property element here instead of delegating it to
{II}# a helper. A call is not free in Python, and this loop runs once for
{II}# every property of every instance.
{II}next_event_element = next(iterator, None)
{II}if next_event_element is None:
{III}raise DeserializationException(
{IIII}f"Expected a property element or the end element corresponding "
{IIII}f"to {{element.tag}}, but got the end-of-input"
{III})

{II}next_event, prop_element = next_event_element
{II}if next_event == 'end' and prop_element.tag == element.tag:
{III}# We reached the end element enclosing the properties.
{III}break

{II}if next_event != 'start':
{III}raise DeserializationException(
{IIII}f"Expected a start element corresponding to a property, "
{IIII}f"but got event {{next_event!r}} "
{IIII}f"and element {{prop_element.tag!r}}"
{III})

{II}try:
{III}tag_wo_ns = _parse_element_tag(prop_element)

{III}reader = readers.get(tag_wo_ns, None)
{III}if reader is None:
{IIII}raise DeserializationException(
{IIIII}f"Expected an element representing a property, "
{IIIII}f"but got an element with unexpected tag: {{tag_wo_ns!r}}"
{IIII})

{III}values[tag_wo_ns] = reader(prop_element, iterator)
{II}except DeserializationException as exception:
{III}exception.path._prepend(ElementSegment(prop_element))
{III}raise

{I}return values"""
        ),
        "_read_list_of_items": Stripped(
            f"""\
def _read_list_of_items(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}read_item: _ContentReader[_ValueT]
) -> List[_ValueT]:
{I}\"\"\"
{I}Read the children of :paramref:`element` as a list of items.

{I}:paramref:`read_item` is responsible for verifying the tag of each item
{I}element itself -- *e.g.*, by wrapping a scalar/enumeration reader with
{I}:py:func:`_read_named_element`, or by relying on a class's own dispatch by
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

{I}result = []  # type: List[_ValueT]

{I}while True:
{II}# NOTE (mristin):
{II}# We pull the next item element here instead of delegating it to a helper,
{II}# as this loop runs once for every item of every list.
{II}next_event_element = next(iterator, None)
{II}if next_event_element is None:
{III}raise DeserializationException(
{IIII}f"Expected an item element or the end element corresponding "
{IIII}f"to {{element.tag}}, but got the end-of-input"
{III})

{II}next_event, item_element = next_event_element
{II}if next_event == 'end' and item_element.tag == element.tag:
{III}# We reached the end element enclosing the items.
{III}break

{II}if next_event != 'start':
{III}raise DeserializationException(
{IIII}f"Expected a start element corresponding to an item, "
{IIII}f"but got event {{next_event!r}} "
{IIII}f"and element {{item_element.tag!r}}"
{III})

{II}try:
{III}item = read_item(item_element, iterator)
{II}except DeserializationException as exception:
{III}exception.path._prepend(IndexSegment(item_element, len(result)))
{III}raise

{II}result.append(item)

{I}return result"""
        ),
        "_read_tuple_item": Stripped(
            f"""\
def _read_tuple_item(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}index: int,
{I}read_item: _ContentReader[_ValueT]
) -> _ValueT:
{I}\"\"\"
{I}Read the item at :paramref:`index` of the tuple enclosed in :paramref:`element`.

{I}:param element: start element enclosing the tuple
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param index: index of the item in the tuple
{I}:param read_item: to read the item, including its own end element
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed item
{I}\"\"\"
{I}next_event_element = next(iterator, None)
{I}if next_event_element is None:
{II}raise DeserializationException(
{III}f"Expected the item {{index}} of the tuple, "
{III}f"but got end-of-input"
{II})

{I}next_event, item_element = next_event_element
{I}if next_event != 'start':
{II}raise DeserializationException(
{III}f"Expected a start element corresponding to the item {{index}} "
{III}f"of the tuple, but got event {{next_event!r}} "
{III}f"and element {{item_element.tag!r}}"
{II})

{I}try:
{II}return read_item(item_element, iterator)
{I}except DeserializationException as exception:
{II}exception.path._prepend(IndexSegment(item_element, index))
{II}raise"""
        ),
        "_read_instance_from_iterparse": Stripped(
            f"""\
def _read_instance_from_iterparse(
{I}iterator: Iterator[Tuple[str, Element]],
{I}read_as_element: _ContentReader[_ValueT],
{I}expected_what: str
) -> _ValueT:
{I}\"\"\"
{I}Read an instance from :paramref:`iterator`, starting at its start element.

{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param read_as_element: to read the instance, including its end element
{I}:param expected_what: what we expected to read, for the error messages
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed instance
{I}\"\"\"
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

{I}try:
{II}return read_as_element(next_element, iterator)
{I}except DeserializationException as exception:
{II}exception.path._prepend(ElementSegment(next_element))
{II}raise exception"""
        ),
        "_collapse_whitespace": Stripped(
            f'''\
_XS_WHITESPACE_RE = re.compile(r"[ \\t\\n\\r]+")


def _collapse_whitespace(text: str) -> str:
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
{I}return _XS_WHITESPACE_RE.sub(" ", text).strip(" ")'''
        ),
        "_read_text_from_element": Stripped(
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
        "_read_bool_from_element_text": Stripped(
            f"""\
_XS_BOOLEAN_LITERAL_SET = {{
{I}"1",
{I}"true",
{I}"0",
{I}"false",
}}


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
{I}text = _collapse_whitespace(
{II}_read_text_from_element(
{III}element,
{III}iterator
{II})
{I})

{I}if text not in _XS_BOOLEAN_LITERAL_SET:
{II}raise DeserializationException(
{III}f"Expected a boolean, "
{III}f"but got an element with text: {{text!r}}"
{II})

{I}return text in ('1', 'true')"""
        ),
        "_read_int_from_element_text": Stripped(
            f"""\
#: Match the lexical space of ``xs:long``.
#:
#: Mind the explicit ``[0-9]``: ``\\d`` would match a digit of any script.
#:
#: See: https://www.w3.org/TR/xmlschema-2/#long
_XS_LONG_RE = re.compile(r"(\\+|-)?[0-9]+")


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
{I}text = _collapse_whitespace(
{II}_read_text_from_element(
{III}element,
{III}iterator
{II})
{I})

{I}# NOTE (mristin):
{I}# ``int`` is far too permissive to be handed the text directly: it takes
{I}# a digit group separator as in ``1_0``, surrounding whitespace, and
{I}# a digit of any script -- the Arabic-Indic ``\u06f5`` would be read as 5.
{I}# Mind that it is checked with ``fullmatch`` and not with ``match``: ``$``
{I}# would also match just before a trailing newline.
{I}#
{I}# See: https://www.w3.org/TR/xmlschema-2/#long
{I}if _XS_LONG_RE.fullmatch(text) is None:
{II}raise DeserializationException(
{III}f"Expected a value as xs:long, "
{III}f"but got an element with text: {{text!r}}"
{II})

{I}try:
{II}value = int(text)
{I}except ValueError:
{II}# pylint: disable=raise-missing-from
{II}raise DeserializationException(
{III}f"Expected an integer, "
{III}f"but got an element with text: {{text!r}}"
{II})

{I}# NOTE (mristin):
{I}# An ``int`` is unbounded in Python, while ``xs:long`` is a 64-bit integer,
{I}# so the range has to be checked explicitly. Every other target gets this
{I}# for free from a parser which refuses what does not fit.
{I}if value < -9223372036854775808 or value > 9223372036854775807:
{II}raise DeserializationException(
{III}f"Expected a value as xs:long, "
{III}f"but got an element with text out of its range: {{text!r}}"
{II})

{I}return value"""
        ),
        "_read_float_from_element_text": Stripped(
            f"""\
_TEXT_TO_XS_DOUBLE_LITERALS = {{
{I}"NaN": math.nan,
{I}"INF": math.inf,
{I}"-INF": -math.inf,
}}

#: Match the numeric part of the lexical space of ``xs:double``. The three
#: named literals are looked up in :py:attr:`_TEXT_TO_XS_DOUBLE_LITERALS`
#: before this is tried.
#:
#: Mind the explicit ``[0-9]``: ``\\d`` would match a digit of any script, so
#: the Arabic-Indic ``\u06f5`` would pass, and :py:func:`float` would read it
#: as 5.
#:
#: See: https://www.w3.org/TR/xmlschema-2/#double
_XS_DOUBLE_RE = re.compile(
{I}r"(\\+|-)?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([Ee](\\+|-)?[0-9]+)?"
)


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
{I}text = _collapse_whitespace(
{II}_read_text_from_element(
{III}element,
{III}iterator
{II})
{I})

{I}value = _TEXT_TO_XS_DOUBLE_LITERALS.get(text, None)
{I}if value is None:
{II}# NOTE (mristin):
{II}# ``float`` is far too permissive to be handed the text directly: it
{II}# takes ``Infinity``, ``inf``, ``nan`` and ``NAN``, none of which is
{II}# a valid ``xs:double``, as well as a digit group separator as in
{II}# ``1_0`` and surrounding whitespace. Mind that it is checked with
{II}# ``fullmatch`` and not with ``match``: ``$`` would also match just
{II}# before a trailing newline.
{II}if _XS_DOUBLE_RE.fullmatch(text) is None:
{III}raise DeserializationException(
{IIII}f"Expected a value as xs:double, "
{IIII}f"but got an element with text: {{text!r}}"
{III})

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
        "_read_str_from_element_text": Stripped(
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
{I}# NOTE (mristin):
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
        "_read_bytes_from_element_text": Stripped(
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
        "_read_enum_from_element_text": Stripped(
            f"""\
def _read_enum_from_element_text(
{I}element: Element,
{I}iterator: Iterator[Tuple[str, Element]],
{I}literal_from_str: Callable[[str], Optional[_ValueT]],
{I}enum_name: str
) -> _ValueT:
{I}\"\"\"
{I}Parse the text of :paramref:`element` as an enumeration literal, and read
{I}the corresponding end element from :paramref:`iterator`.

{I}:param element: start element
{I}:param iterator:
{II}Input stream of ``(event, element)`` coming from
{II}:py:func:`xml.etree.ElementTree.iterparse` with the argument
{II}``events=["start", "end"]``
{I}:param literal_from_str: to parse the literal from its string representation
{I}:param enum_name: name of the enumeration, for the error messages
{I}:raise: :py:class:`DeserializationException` if unexpected input
{I}:return: parsed literal
{I}\"\"\"
{I}text = _read_text_from_element(
{II}element,
{II}iterator
{I})

{I}literal = literal_from_str(text)
{I}if literal is None:
{II}raise DeserializationException(
{III}f"Not a valid string representation of "
{III}f"a literal of {{enum_name}}: {{text}}"
{II})

{I}return literal"""
        ),
    }


def _generate_writing_helpers() -> Mapping[str, Stripped]:
    """
    Generate the code of the shared writing helpers, by the name of the helper.

    Every helper shares the shape of a writer,
    ``(name, prop_name, value, serializer) 🠒 None``, save for
    :py:func:`_write_list_of_items` which is additionally given the writer of its
    items. Only the helpers which a meta-model reaches are finally generated, see
    :py:func:`_collect_needed_helpers`, so that a small meta-model does not pay for
    the writers which it never calls.

    Every helper funnels its failures through ``_attribute_to_property``, and the two
    helpers which write a collection funnel the failure of an item through
    ``_attribute_to_item`` first, so that the path to the culprit falls out as
    the stack unwinds.
    """
    return {
        "_write_bool_as_element": Stripped(
            f"""\
def _write_bool_as_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: bool,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a boolean enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)
{II}serializer.stream.write('true' if value else 'false')
{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_int_as_element": Stripped(
            f"""\
def _write_int_as_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: int,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of an integer enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)
{II}serializer.stream.write(str(value))
{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_float_as_element": Stripped(
            f"""\
def _write_float_as_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: float,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a floating-point number enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)

{II}if value == math.inf:
{III}serializer.stream.write('INF')
{II}elif value == -math.inf:
{III}serializer.stream.write('-INF')
{II}elif math.isnan(value):
{III}serializer.stream.write('NaN')
{II}elif value == 0:
{III}if math.copysign(1.0, value) < 0.0:
{IIII}serializer.stream.write('-0.0')
{III}else:
{IIII}serializer.stream.write('0.0')
{II}else:
{III}serializer.stream.write(str(value))

{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_str_as_element": Stripped(
            f"""\
def _write_str_as_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: str,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a string enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)

{II}# NOTE (mristin):
{II}# We ran ``timeit`` on manual code which escaped XML special characters with
{II}# a dictionary, and on another snippet which called three ``.replace()``.
{II}# The code with ``.replace()`` was an order of magnitude faster on our
{II}# computers.
{II}#
{II}# The escaping is written out here, and not put in a function of its own,
{II}# since a string is the commonest value in a meta-model and a call is not free.
{II}serializer.stream.write(
{III}value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
{II})

{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_bytes_as_element": Stripped(
            f"""\
def _write_bytes_as_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: bytes,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the :paramref:`value` of a binary content enclosed in
{I}the :paramref:`name` element.

{I}:param name: of the corresponding element tag
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)

{II}# NOTE (mristin):
{II}# We need to decode the result of the base64-encoding to ASCII since we are
{II}# writing to an XML *text* stream. ``base64.b64encode(.)`` gives us bytes,
{II}# not a string.
{II}encoded = base64.b64encode(value).decode('ascii')

{II}# NOTE (mristin):
{II}# Base64 alphabet excludes ``<``, ``>`` and ``&``, so we can directly
{II}# write the ``encoded`` content to the stream as XML text.
{II}#
{II}# See: https://datatracker.ietf.org/doc/html/rfc4648#section-4
{II}serializer.stream.write(encoded)
{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_enum_as_element": Stripped(
            f"""\
def _write_enum_as_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: enum.Enum,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write the literal :paramref:`value` enclosed in the :paramref:`name` element.

{I}A literal is written as the text of the element, so this one writer serves every
{I}enumeration of the meta-model. The access to the literal's value is deliberately
{I}*not* spelled out at the call site: a :paramref:`value` which is not a literal
{I}of the enumeration would then break *before* this function is entered, and
{I}the failure could no longer be attributed to :paramref:`prop_name`.

{I}:param name: of the corresponding element tag
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}_write_str_as_element(name, None, value.value, serializer)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_nested_element": Stripped(
            f"""\
def _write_nested_element(
{I}name: str,
{I}prop_name: Optional[str],
{I}value: aas_types.Class,
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write :paramref:`value` nested in the :paramref:`name` element.

{I}The instance writes the element which designates its model type, so it has to be
{I}nested in an element of its own when it is the value of a property. Mind that
{I}an *item* of a list is not nested that way -- see
{I}:py:func:`_write_list_of_instances` -- as it is the item's own element which
{I}already sits in the list's element.

{I}The element which designates the model type contributes no segment to the path
{I}of a :py:class:`SerializationException`. The path points into the instance which
{I}was handed over for the serialization, and there that element is no level of its
{I}own: ``.value.id_short`` is exactly what you would write in Python.

{I}:param name: of the enclosing element
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param value: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}serializer._write_start_element(name)
{II}serializer.visit(value)
{II}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_list_of_instances": Stripped(
            f"""\
def _write_list_of_instances(
{I}name: str,
{I}prop_name: Optional[str],
{I}items: Sequence[aas_types.Class],
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write :paramref:`items` enclosed in the :paramref:`name` element.

{I}Every item writes the element which designates its model type, so no positional
{I}tag is necessary. If there are no items, the enclosing element is collapsed to
{I}an empty one.

{I}:param name: of the enclosing element
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param items: to be serialized
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}if len(items) == 0:
{III}serializer._write_empty_element(name)
{II}else:
{III}serializer._write_start_element(name)

{III}for index, item in enumerate(items):
{IIII}try:
{IIIII}serializer.visit(item)
{IIII}except Exception as exception:
{IIIII}_attribute_to_item(exception, index)

{III}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
        "_write_list_of_items": Stripped(
            f"""\
def _write_list_of_items(
{I}name: str,
{I}prop_name: Optional[str],
{I}items: Sequence[_ItemT],
{I}write_item: '_ElementWriter[_ItemT]',
{I}serializer: '_Serializer'
) -> None:
{I}\"\"\"
{I}Write :paramref:`items` enclosed in the :paramref:`name` element.

{I}An item is encoded as the text of an element, so it is not self-describing, and
{I}every item is written in an element tagged ``v``. If there are no items,
{I}the enclosing element is collapsed to an empty one.

{I}:param name: of the enclosing element
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:param items: to be serialized
{I}:param write_item: to write a single item of :paramref:`items`
{I}:param serializer: to write to
{I}:raise: :py:class:`SerializationException` if the value could not be written
{I}\"\"\"
{I}try:
{II}if len(items) == 0:
{III}serializer._write_empty_element(name)
{II}else:
{III}serializer._write_start_element(name)

{III}for index, item in enumerate(items):
{IIII}try:
{IIIII}write_item('v', None, item, serializer)
{IIII}except Exception as exception:
{IIIII}_attribute_to_item(exception, index)

{III}serializer._write_end_element(name)
{I}except Exception as exception:
{II}_attribute_to_property(exception, prop_name)"""
        ),
    }


assert sorted(_HELPER_DEPENDENCIES.keys()) == sorted(
    list(_generate_reading_helpers().keys()) + list(_generate_writing_helpers().keys())
), (
    "Expected the dependencies to be noted for exactly the generated helpers, "
    "but got: "
    f"{sorted(_HELPER_DEPENDENCIES.keys())} and "
    f"{sorted(list(_generate_reading_helpers().keys()) + list(_generate_writing_helpers().keys()))}"
)


def _collect_needed_helpers(seeds: AbstractSet[str]) -> Set[str]:
    """
    Collect the shared reading helpers which have to be generated for the ``seeds``.

    The result is the ``seeds`` closed over :py:attr:`_HELPER_DEPENDENCIES`: a helper
    is in it if a seed needs it, directly or through another helper. Generating exactly
    these helpers therefore leaves no dangling name in the generated module -- an
    enumeration is read on top of the text path, and a list of enumerations needs the
    enumeration reader even when no property is one.

    The ``seeds`` are noted by :py:class:`_ReaderRegistry` as it walks the meta-model,
    and they also carry the names of the readers which are generated elsewhere: the
    reader of an enumeration comes with the enumeration itself. Such a name is not
    a shared helper, so it is left out, and the result contains only names which
    :py:func:`_generate_reading_helpers` gives out.

    :param seeds: names of the helpers, and of other readers, which are needed
    :return: names of the shared helpers to be generated
    """
    result = set()  # type: Set[str]

    stack = [seed for seed in seeds if seed in _HELPER_DEPENDENCIES]
    while len(stack) > 0:
        helper = stack.pop()
        if helper in result:
            continue

        result.add(helper)
        stack.extend(_HELPER_DEPENDENCIES[helper])

    return result


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
import enum
import io
import math
import os
import re
import sys
from typing import (
{I}Any,
{I}Callable,
{I}Dict,
{I}Iterator,
{I}List,
{I}Mapping,
{I}NoReturn,
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

    # NOTE (mristin):
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

    # region Compose the readers

    # NOTE (mristin):
    # We compose the readers first so that we know which of them, and which of
    # the shared helpers, a meta-model actually reaches. Only those are finally
    # generated, gated along the call graph.

    errors.extend(python_common.errors_in_monikers(symbol_table))

    if len(errors) > 0:
        return None, errors

    registry = _ReaderRegistry()

    reader_blocks = []  # type: List[Stripped]
    readers_map_blocks = []  # type: List[Stripped]

    for concrete_cls in symbol_table.concrete_classes:
        if concrete_cls.is_implementation_specific:
            continue

        for prop in concrete_cls.properties:
            registry.register_content_reader(prop.type_annotation)

        readers_map_blocks.append(_generate_readers_map(cls=concrete_cls))

    # endregion

    # region Generate the readers

    tuple_arities = intermediate.tuple_arities(symbol_table)
    if len(tuple_arities) > 0:
        registry.note_needed_helper("_read_tuple_item")

        reader_blocks.append(
            Stripped(
                "\n".join(
                    f'_TupleItem{i}T = TypeVar("_TupleItem{i}T")'
                    for i in range(1, max(tuple_arities) + 1)
                )
            )
        )
        for arity in tuple_arities:
            reader_blocks.append(_generate_tuple_from_element(arity=arity))

    reader_blocks.extend(registry.blocks)

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            enum_reader = python_naming.private_function_name(
                Identifier(f"read_{our_type.name}_from_element_text")
            )

            if enum_reader in registry.needed_helpers:
                reader_blocks.append(
                    _generate_read_enum_from_element_text(enumeration=our_type)
                )

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            continue

        elif isinstance(our_type, intermediate.AbstractClass):
            reader_blocks.append(_generate_read_cls_as_element(cls=our_type))

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/read_{our_type.name}_as_sequence.py"
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

                # NOTE (mristin):
                # The snippet is expected to define the function which reads
                # the instance as a sequence of the XML-encoded properties. Everything
                # around it -- the dispatch on the element tag and the public
                # functions -- is generated as for any other class.
                reader_blocks.append(implementation)
            else:
                reader_blocks.append(_generate_read_as_sequence(cls=our_type))

            reader_blocks.append(_generate_read_cls_as_element(cls=our_type))

        elif isinstance(our_type, intermediate.NamedUnion):
            reader_blocks.append(
                _generate_read_named_union_as_element(named_union=our_type)
            )

        else:
            assert_never(our_type)

    reader_blocks.append(_generate_general_read_as_element(symbol_table=symbol_table))

    for cls in symbol_table.classes:
        if isinstance(cls, intermediate.AbstractClass):
            reader_blocks.append(_generate_dispatch_map_for_class(cls=cls))
        elif isinstance(cls, intermediate.ConcreteClass):
            if len(cls.concrete_descendants) > 0:
                reader_blocks.append(_generate_dispatch_map_for_class(cls=cls))
        else:
            assert_never(cls)

    for named_union in symbol_table.named_unions:
        reader_blocks.append(
            _generate_dispatch_map_for_named_union(named_union=named_union)
        )

    reader_blocks.append(_generate_general_dispatch_map(symbol_table=symbol_table))

    reader_blocks.extend(readers_map_blocks)

    if len(errors) > 0:
        return None, errors

    # endregion

    # region Generate the shared helpers which the readers need

    # NOTE (mristin):
    # The public functions start every reading, and an instance is always dispatched
    # on its own tag, so these two are needed for any meta-model.
    registry.note_needed_helper("_read_dispatched")
    registry.note_needed_helper("_read_instance_from_iterparse")

    if any(
        not concrete_cls.is_implementation_specific
        for concrete_cls in symbol_table.concrete_classes
    ):
        registry.note_needed_helper("_read_properties")

    if any(
        len(concrete_cls.concrete_descendants) == 0
        for concrete_cls in symbol_table.concrete_classes
    ):
        registry.note_needed_helper("_read_named_element")

    helper_blocks = _generate_reading_helpers()

    # NOTE (mristin):
    # We can not see inside a snippet, so we do not know which of the shared helpers
    # it calls. As soon as a meta-model has an implementation-specific class, we
    # therefore generate all of them, instead of letting the snippet fail with
    # a ``NameError`` at the time of the reading.
    if any(
        concrete_cls.is_implementation_specific
        for concrete_cls in symbol_table.concrete_classes
    ):
        for helper_name in helper_blocks:
            registry.note_needed_helper(helper_name)

    needed_helpers = _collect_needed_helpers(registry.needed_helpers)

    blocks.append(_READING_PATTERN_NOTE)

    blocks.append(
        Stripped(
            f"""\
_ValueT = TypeVar("_ValueT")

#: Read the content of an element which has already been opened, and read
#: the corresponding end element as well
_ContentReader = Callable[
{I}[Element, Iterator[Tuple[str, Element]]],
{I}_ValueT
]"""
        )
    )

    blocks.extend(
        block for name, block in helper_blocks.items() if name in needed_helpers
    )

    # endregion

    blocks.extend(reader_blocks)

    blocks.append(Stripped("# endregion"))

    blocks.append(Stripped("# region Serialization"))

    # region Compose the writers

    # NOTE (mristin):
    # As on the reading side, we compose the writers first so that we know which of
    # them, and which of the shared helpers, a meta-model actually reaches. Only those
    # are finally generated, gated along the call graph.

    writer_registry = _WriterRegistry()

    for concrete_cls in symbol_table.concrete_classes:
        # NOTE (mristin):
        # The content of an implementation-specific class is written by a snippet,
        # so the writers which its properties would need are never called. We skip
        # it here, as the reading side does, and the snippet is on its own.
        if concrete_cls.is_implementation_specific:
            continue

        for prop in concrete_cls.properties:
            writer_registry.register_property_writer(prop.type_annotation)

    writing_helper_blocks = _generate_writing_helpers()

    # NOTE (mristin):
    # As on the reading side, we can not see inside a snippet, so all the shared
    # helpers are generated as soon as a meta-model has an implementation-specific
    # class.
    if any(
        concrete_cls.is_implementation_specific
        for concrete_cls in symbol_table.concrete_classes
    ):
        for helper_name in writing_helper_blocks:
            writer_registry.note_needed_helper(helper_name)

    # NOTE (mristin):
    # An instance is nested in the element of a property, and the element of a class
    # is written by the writer generated together with the class, so the only helpers
    # which are always needed are the ones which the visits reach.
    needed_writing_helpers = _collect_needed_helpers(writer_registry.needed_helpers)

    # endregion

    # region Generate the writers

    # NOTE (mristin):
    # The serialization is not total: the stream can fail, and the type annotations
    # of a meta-model are not enforced at run-time, so a property can hold a value
    # which we can not serialize. Every writer therefore funnels its failures through
    # ``_attribute_to_property`` and ``_attribute_to_item`` below, which build up
    # the path to the culprit as the stack unwinds.
    blocks.append(
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

{I}def __str__(self) -> str:
{II}if len(self._segments) == 0:
{III}return self.cause

{II}return f'{{self.path}}: {{self.cause}}'"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
def _attribute_to_property(
{II}exception: Exception,
{II}prop_name: Optional[str]
) -> NoReturn:
{I}\"\"\"
{I}Re-raise the :paramref:`exception` as a failure of the property
{I}:paramref:`prop_name`.

{I}Every writer funnels its failures through this function, so that the path to
{I}the culprit is built up as the stack unwinds: a writer knows the property whose
{I}value it writes, and nothing below it does.

{I}A :paramref:`prop_name` of ``None`` prepends nothing to the path. It does *not*
{I}mean that no property is involved. It means that the access which leads to
{I}the value is recorded by a writer further up the stack, so recording it here
{I}as well would spell one step of the path twice.

{I}For example, the writer of an item of a list is given no property name. The list
{I}writer records its own property and the loop over the items records the index, so
{I}that ``.submodel_elements[3]`` is assembled from ``submodel_elements`` above and
{I}``3`` around the item. Were the item to contribute ``submodel_elements`` as well,
{I}the path would read ``.submodel_elements[3].submodel_elements``.

{I}Likewise, an instance nested in the element of a property is written by
{I}a dispatch on its run-time type, and a dispatch knows nothing about where
{I}the instance came from. It is :py:func:`_write_nested_element` above it which
{I}knows that the instance sits in ``.value``, so the writer which the dispatch
{I}selects contributes no segment of its own.

{I}The path therefore stays empty only when the value which broke *is* the one you
{I}handed over, which is the failure :py:func:`write` funnels here: there is no
{I}access leading to it to report.

{I}We deliberately catch *any* exception, and not only the failures of
{I}the underlying stream. The type annotations are not enforced at run-time, so
{I}a property can hold a value which we can not serialize, and telling you where
{I}that value sits is much more helpful than the bare exception. The original
{I}exception is kept as the cause of the raised one.

{I}:param exception: to be re-raised
{I}:param prop_name:
{II}name of the property, as spelled in Python, whose value is written, or
{II}``None`` if the access to the value is recorded by an enclosing writer
{I}:raise: :py:class:`SerializationException` always
{I}\"\"\"
{I}if isinstance(exception, SerializationException):
{II}if prop_name is not None:
{III}exception._prepend_property(prop_name)

{II}raise exception

{I}failure = SerializationException(str(exception))
{I}if prop_name is not None:
{II}failure._prepend_property(prop_name)

{I}raise failure from exception"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
def _attribute_to_item(
{II}exception: Exception,
{II}index: int
) -> NoReturn:
{I}\"\"\"
{I}Re-raise the :paramref:`exception` as a failure of the item at
{I}:paramref:`index`.

{I}This is the counterpart of :py:func:`_attribute_to_property` for the items of
{I}a list and of a tuple. The item's own element contributes no segment to
{I}the path: an item is selected by its position, and not by its element tag.

{I}:param exception: to be re-raised
{I}:param index: of the item which was being written
{I}:raise: :py:class:`SerializationException` always
{I}\"\"\"
{I}if isinstance(exception, SerializationException):
{II}exception._prepend_index(index)
{II}raise exception

{I}failure = SerializationException(str(exception))
{I}failure._prepend_index(index)
{I}raise failure from exception"""
        )
    )

    if "_write_list_of_items" in needed_writing_helpers:
        blocks.append(
            Stripped(
                f"""\
_ItemT = TypeVar("_ItemT")

#: Write a value as a whole XML element, the element tag included
_ElementWriter = Callable[
{I}[str, Optional[str], _ValueT, '_Serializer'],
{I}None
]"""
            )
        )

    blocks.extend(
        block
        for name, block in writing_helper_blocks.items()
        if name in needed_writing_helpers
    )

    blocks.extend(writer_registry.blocks)

    for concrete_cls in symbol_table.concrete_classes:
        if concrete_cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Xmlization/write_{concrete_cls.name}_as_sequence.py"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        concrete_cls.parsed.node,
                        f"The xmlization snippet is missing "
                        f"for the implementation-specific "
                        f"class {concrete_cls.name}: {implementation_key}",
                    )
                )
                continue

            # NOTE (mristin):
            # The snippet is expected to define the function which writes the content
            # of the element, the properties of the instance. The element around it is
            # framed by the generated writer, so that the snippet needs to know
            # nothing about the element tag or about the namespace which only the very
            # first element specifies.
            blocks.append(implementation)

        blocks.append(_generate_write_cls_as_element(cls=concrete_cls))

    if len(errors) > 0:
        return None, errors

    # endregion

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
{I}:raise:
{II}:py:class:`SerializationException` if :paramref:`that` could not be
{II}serialized
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
