"""Provide code generation for unrolling recursive calls and iterations."""
import abc
import io
import textwrap
from typing import Sequence, List

from icontract import DBC, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import assert_never
from aas_core_codegen.python.common import INDENT as I


class Node:
    """Represent a node in the unrolling tree."""

    def __init__(self, text: str, children: Sequence["Node"]):
        self.text = text
        self.children = children


def render(node: Node) -> str:
    """
    Render the node recursively.

    >>> render(Node(text='something', children=[]))
    'something'

    >>> render(Node(text='parent', children=[Node(text='child', children=[])]))
    'parent\\n    child'

    >>> render(Node(text='parent', children=[
    ...     Node(text='child1', children=[]),
    ...     Node(text='child2', children=[]),
    ... ]))
    'parent\\n    child1\\n\\n    child2'
    """
    if len(node.children) == 0:
        return node.text

    writer = io.StringIO()
    writer.write(node.text)

    for i, child in enumerate(node.children):
        if i == 0:
            writer.write("\n")
        else:
            writer.write("\n\n")

        writer.write(textwrap.indent(render(child), I))

    return writer.getvalue()


class AbstractUnroller(DBC):
    """Generate code to unroll recursion into generic types."""

    @abc.abstractmethod
    def _unroll_primitive_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.PrimitiveTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_our_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OurTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_list_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.ListTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_tuple_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TupleTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_optional_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OptionalTypeAnnotation,
        path: List[str],
        list_loop_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @require(lambda list_loop_level: list_loop_level >= 0)
    def unroll(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TypeAnnotationUnion,
        path: List[str],
        list_loop_level: int,
    ) -> List[Node]:
        """
        Dispatch the given type annotation to unrolling.

        :param unrollee_expr: Expression of the element to be unrolled
        :param type_annotation: Type annotation corresponding to the ``unrollee_expr``
        :param path:
            Path, as code snippets to be joined by "/" to the ``unrollee_expr``
        :param list_loop_level:
            Depth level of the list loops.

            Level 0 indicates the outer loop.
        """
        if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
            return self._unroll_primitive_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                list_loop_level=list_loop_level,
            )

        elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
            return self._unroll_our_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                list_loop_level=list_loop_level,
            )

        elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
            return self._unroll_list_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                list_loop_level=list_loop_level,
            )

        elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
            return self._unroll_tuple_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                list_loop_level=list_loop_level,
            )

        elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
            return self._unroll_optional_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                list_loop_level=list_loop_level,
            )
        else:
            assert_never(type_annotation)

        raise AssertionError("Should not have gotten here")
