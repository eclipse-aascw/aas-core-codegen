"""Generate code of visitors to iterate over instances."""

import io
import textwrap
from typing import Tuple, Optional, List

from icontract import ensure

import aas_core_codegen.csharp.common as csharp_common
import aas_core_codegen.csharp.naming as csharp_naming
from aas_core_codegen import intermediate
from aas_core_codegen.common import Error, Stripped, Rstripped, Identifier
from aas_core_codegen.csharp.common import INDENT as I, INDENT2 as II


def _generate_ivisitor(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the visitor interface."""
    blocks = []  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not visit
    # them.
    for cls in symbol_table.concrete_classes:
        # NOTE (mristin): Operate on interfaces instead of classes
        # We operate on *interfaces* instead of concrete classes to allow for
        # custom extensions and wrappers around our model classes.
        #
        # Originally, we used type overloading to dispatch the visit calls. After we
        # decided to support custom wrappers and enhancements to our classes, we had
        # to switch here to interfaces instead of concrete classes. The type
        # overloading does not work anymore in this setting, as descendants of
        # *concrete* classes would be wrongly dispatched. That is why we dispatch
        # explicitly, by having different visit method names instead of mere
        # type overloads.

        interface_name = csharp_naming.interface_name(cls.name)
        visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public void {visit_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Define the interface for a visitor which visits the instances of the model.
/// </summary>
/// <remarks>
/// When you use the visitor, please always call the main dispatching method
/// <see cref="Visit" />. You should most probably never call the <c>Visit*</c>
/// methods directly. They are only made public so that model classes can access them.
/// </remarks>
public interface IVisitor
{{
{I}public void Visit(IClass that);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public interface IVisitor")

    return Stripped(writer.getvalue())


def _generate_visitor_through(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the visitor that simply iterates over the instances."""
    blocks = [
        Stripped(
            f"""\
public virtual void Visit(IClass that)
{{
{I}that.Accept(this);
}}"""
        )
    ]  # type: List[Stripped]

    # Abstract classes are modeled as interfaces in C#, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public virtual void {visit_name}(
{I}{interface_name} that
)
{{
{I}// Just descend through, do nothing with <c>that</c>
{I}foreach (var something in that.DescendOnce())
{I}{{
{II}Visit(something);
{I}}}
}}"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/// <summary>
/// Just descend through the instances without any action.
/// </summary>
/// <remarks>
/// This class is meaningless for itself. However, it is a good base if you
/// want to descend through instances and apply actions only on a subset of
/// classes.
/// </remarks>
public class VisitorThrough : IVisitor
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public class VisitorThrough")

    return Stripped(writer.getvalue())


def _generate_abstract_visitor(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the visitor that performs double-dispatch."""
    blocks = [
        Stripped(
            f"""\
public virtual void Visit(IClass that)
{{
{I}that.Accept(this);
}}"""
        )
    ]  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract void {visit_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/// <summary>
/// Perform double-dispatch to visit the concrete instances.
/// </summary>
public abstract class AbstractVisitor : IVisitor
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public abstract class AbstractVisitor")

    return Stripped(writer.getvalue())


def _generate_ivisitor_with_context(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the interface for the visitor with context."""
    blocks = []  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not visit
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public void {visit_name}(
{I}{interface_name} that,
{I}TContext context
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Define the interface for a visitor which visits the instances of the model.
/// </summary>
/// <remarks>
/// When you use the visitor, please always call the main dispatching method
/// <see cref="Visit" />. You should most probably never call the <c>Visit*</c>
/// methods directly. They are only made public so that model classes can access them.
/// </remarks>
/// <typeparam name="TContext">Context type</typeparam>
public interface IVisitorWithContext<in TContext>
{{
{I}public void Visit(IClass that, TContext context);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public interface IVisitorWithContext")

    return Stripped(writer.getvalue())


def _generate_abstract_visitor_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the visitor with context that performs double-dispatch."""
    blocks = [
        Stripped(
            f"""\
public virtual void Visit(IClass that, TContext context)
{{
{I}that.Accept(this, context);
}}"""
        )
    ]  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not visit
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract void {visit_name}(
{I}{interface_name} that,
{I}TContext context
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Perform double-dispatch to visit the concrete instances
/// with context.
/// </summary>
/// <typeparam name="TContext">Context type</typeparam>
public abstract class AbstractVisitorWithContext<TContext>
{I}: IVisitorWithContext<TContext>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public abstract class AbstractVisitorWithContext")

    return Stripped(writer.getvalue())


def _generate_itransformer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the transformer interface."""
    blocks = []  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public T {transform_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Define the interface for a transformer which transforms recursively
/// the instances into something else.
/// </summary>
/// <remarks>
/// When you use the transformer, please always call the main dispatching method
/// <see cref="Transform" />. You should most probably never call the <c>Transform*</c>
/// methods directly. They are only made public so that model classes can access them.
/// </remarks>
/// <typeparam name="T">The type of the transformation result</typeparam>
public interface ITransformer<out T>
{{
{I}public T Transform(IClass that);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public interface ITransformer")

    return Stripped(writer.getvalue())


def _generate_abstract_transformer(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the most abstract transformer that merely double-dispatches."""
    blocks = [
        Stripped(
            f"""\
public virtual T Transform(IClass that)
{{
{I}return that.Transform(this);
}}"""
        )
    ]  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract T {transform_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        """\
/// <summary>
/// Perform double-dispatch to transform recursively
/// the instances into something else.
/// </summary>
/// <typeparam name="T">The type of the transformation result</typeparam>
public abstract class AbstractTransformer<T> : ITransformer<T>
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public abstract class AbstractTransformer")

    return Stripped(writer.getvalue())


def _generate_itransformer_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the interface for the transformer with context."""
    blocks = []  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public T {transform_name}(
{I}{interface_name} that,
{I}TContext context
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Define the interface for a transformer which recursively transforms
/// the instances into something else while the context is passed along.
/// </summary>
/// <remarks>
/// When you use the transformer, please always call the main dispatching method
/// <see cref="Transform" />. You should most probably never call the <c>Transform*</c>
/// methods directly. They are only made public so that model classes can access them.
/// </remarks>
/// <typeparam name="TContext">Type of the transformation context</typeparam>
/// <typeparam name="T">The type of the transformation result</typeparam>
public interface ITransformerWithContext<in TContext, out T>
{{
{I}public T Transform(IClass that, TContext context);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public interface ITransformerWithContext")

    return Stripped(writer.getvalue())


def _generate_abstract_transformer_with_context(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the most abstract transformer that merely double-dispatches."""
    blocks = [
        Stripped(
            f"""\
public virtual T Transform(IClass that, TContext context)
{{
{I}return that.Transform(this, context);
}}"""
        )
    ]  # type: List[Stripped]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        # See the note: "Operate on interfaces instead of classes"

        interface_name = csharp_naming.interface_name(cls.name)
        transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract T {transform_name}(
{I}{interface_name} that,
{I}TContext context
);"""
            )
        )

    writer = io.StringIO()
    writer.write(
        f"""\
/// <summary>
/// Perform double-dispatch to transform recursively
/// the instances into something else.
/// </summary>
/// <remarks>
/// When you use the transformer, please always call the main dispatching method
/// <see cref="Transform" />. You should most probably never call the <c>Transform*</c>
/// methods directly. They are only made public so that model classes can access them.
/// </remarks>
/// <typeparam name="TContext">The type of the transformation context</typeparam>
/// <typeparam name="T">The type of the transformation result</typeparam>
public abstract class AbstractTransformerWithContext<TContext, T>
{I}: ITransformerWithContext<TContext, T>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // public abstract class AbstractTransformerWithContext")

    return Stripped(writer.getvalue())


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable, namespace: csharp_common.NamespaceIdentifier
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code of visitors to iterate over instances.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    blocks = [csharp_common.WARNING]  # type: List[Rstripped]

    writer = io.StringIO()
    writer.write(f"namespace {namespace}\n{{\n")
    writer.write(
        f"""\
{I}public static class Visitation
{I}{{
"""
    )

    visitation_blocks = [
        _generate_ivisitor(symbol_table=symbol_table),
        _generate_visitor_through(symbol_table=symbol_table),
        _generate_abstract_visitor(symbol_table=symbol_table),
        _generate_ivisitor_with_context(symbol_table=symbol_table),
        _generate_abstract_visitor_with_context(symbol_table=symbol_table),
        _generate_itransformer(symbol_table=symbol_table),
        _generate_abstract_transformer(symbol_table=symbol_table),
        _generate_itransformer_with_context(symbol_table=symbol_table),
        _generate_abstract_transformer_with_context(symbol_table=symbol_table),
    ]

    for i, visitation_block in enumerate(visitation_blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(visitation_block, II))

    writer.write(f"\n{I}}}  // public static class Visitation")
    writer.write(f"\n}}  // namespace {namespace}")

    blocks.append(Stripped(writer.getvalue()))

    blocks.append(csharp_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
