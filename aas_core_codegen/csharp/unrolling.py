"""Provide code generation for unrolling recursive calls and iterations."""
import abc
import io
import textwrap
from typing import Sequence, List

from icontract import DBC, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, assert_never
from aas_core_codegen.csharp.common import INDENT as I


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
    'parent\\n{\\n    child\\n}'

    >>> render(Node(text='parent', children=[
    ...     Node(text='child1', children=[]),
    ...     Node(text='child2', children=[]),
    ... ]))
    'parent\\n{\\n    child1\\n\\n    child2\\n}'
    """
    if len(node.children) == 0:
        return node.text

    writer = io.StringIO()
    writer.write(node.text)
    writer.write("\n{")

    for i, child in enumerate(node.children):
        if i == 0:
            writer.write("\n")
        else:
            writer.write("\n\n")

        writer.write(textwrap.indent(render(child), I))

    writer.write("\n}")

    return writer.getvalue()


class AbstractUnroller(DBC):
    """Generate code to unroll recursion into generic types."""

    # NOTE (mristin, 2022-09-15):
    # We originally wrote this code to unroll both lists *and* dictionaries. Eventually,
    # no dictionaries were included in the meta-model. Due to the lack of time, we could
    # not clean up the implementation of this class. Additionally, it is well possible
    # that the dictionaries will be introduced eventually in the meta-model, so we leave
    # the code as-is at the moment.
    #
    # If you read this comment, have to change this class and the dictionaries are not
    # part of the meta-model yet, please go ahead and clean it up first.

    @staticmethod
    @require(lambda level: level >= 0)
    @require(lambda suffix: suffix in ("Item", "KeyValue"))
    def _loop_var_name(level: int, suffix: str) -> Identifier:
        """
        Generate the name of the loop variable.

        :param level:
            recursion level

            The level 0 implies the first inner loop.
        :param suffix:
            suffix of the loop variable; we distinguish between items in a list and
            key-value-pairs in a dictionary
        :return: generated loop variable name
        """
        if level == 0:
            if suffix == "Item":
                return Identifier(f"an{suffix}")
            else:
                assert suffix == "KeyValue"
                return Identifier(f"a{suffix}")

        elif level == 1:
            return Identifier(f"another{suffix}")
        else:
            return Identifier("yet" + "Yet" * (level - 1) + f"another{suffix}")

    @abc.abstractmethod
    def _unroll_primitive_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.PrimitiveTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_our_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OurTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_list_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.ListTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_tuple_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TupleTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _unroll_optional_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OptionalTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[Node]:
        """Generate code for the given specific ``type_annotation``."""
        raise NotImplementedError()

    @require(lambda item_level: item_level >= 0)
    @require(lambda key_value_level: key_value_level >= 0)
    def unroll(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TypeAnnotationUnion,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[Node]:
        """
        Dispatch the given type annotation to unrolling.

        :param unrollee_expr: Expression of the element to be unrolled
        :param type_annotation: Type annotation corresponding to the ``unrollee_expr``
        :param path:
            Path, as code snippets to be joined by "/"to the ``unrollee_expr``
        :param item_level:
            Depth level of the list loops.

            Level 0 indicates the outer loop.
        :param key_value_level:
            Depth level of the key-value-pairs loops.

            Level 0 indicates the outer loop.
        """
        if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
            return self._unroll_primitive_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                item_level=item_level,
                key_value_level=key_value_level,
            )

        elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
            return self._unroll_our_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                item_level=item_level,
                key_value_level=key_value_level,
            )

        elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
            return self._unroll_list_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                item_level=item_level,
                key_value_level=key_value_level,
            )

        elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
            return self._unroll_tuple_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                item_level=item_level,
                key_value_level=key_value_level,
            )

        elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
            return self._unroll_optional_type_annotation(
                unrollee_expr=unrollee_expr,
                type_annotation=type_annotation,
                path=path,
                item_level=item_level,
                key_value_level=key_value_level,
            )
        else:
            assert_never(type_annotation)

        raise AssertionError("Should not have gotten here")
