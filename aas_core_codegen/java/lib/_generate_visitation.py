"""Generate code of visitors to iterate over instances."""

import io
import textwrap
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Identifier,
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
)

# region Generate


def _generate_ivisitor(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the visitor interface."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
    ]

    blocks: List[Stripped] = []

    # Abstract classes have no particular implementation, so we do not visit
    # them.
    for cls in symbol_table.concrete_classes:
        # NOTE (empwilli):
        # Operate on interfaces instead of classes We operate on *interfaces*
        # instead of concrete classes to allow for custom extensions and
        # wrappers around our model classes.
        #
        # Originally, we used type overloading to dispatch the visit calls. After we
        # decided to support custom wrappers and enhancements to our classes, we had
        # to switch here to interfaces instead of concrete classes. The type
        # overloading does not work anymore in this setting, as descendants of
        # *concrete* classes would be wrongly dispatched. That is why we dispatch
        # explicitly, by having different visit method names instead of mere
        # type overloads.
        interface_name = java_naming.interface_name(cls.name)
        visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
void {visit_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        f"""\
/**
 * Define the interface for a visitor which visits the instances of the model.
 *
 * <p>When you use the visitor, please always call the main dispatching method
 * {{@link IVisitor#visit}}. You should most probably never call the {{@code visit*}}
 * methods directly. They are only made public so that model classes can access them.
 */
public interface IVisitor
{{
{I}void visit(IClass that);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_visitor_through(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the visitor that simply iterates over the instances."""
    blocks: List[Stripped] = []

    # Abstract classes are modeled as interfaces in Java, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public void {visit_name}(
{I}{interface_name} that
) {{
{I}// Just descend through, do nothing with {{@code that}}
{I}for (IClass something : that.descendOnce()) {{
{II}visit(something);
{I}}}
}}"""
            )
        )

    visitor_blocks = "\n\n".join(blocks)

    code = Stripped(
        f"""\
import {package}.types.model.*;
import {package}.visitation.IVisitor;

/**
 * Just descend through the instances without any action.
 *
 * <p>This class is meaningless for itself. However, it is a good base if you
 * want to descend through instances and apply actions only on a subset of
 * classes.
 */
public class VisitorThrough implements IVisitor {{
{I}public void visit(IClass that) {{
{II}that.accept(this);
{I}}}

{I}{indent_but_first_line(visitor_blocks, I)}
}}"""
    )

    return code


def _generate_abstract_visitor(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the visitor that performs double-dispatch."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.IVisitor;"),
    ]

    blocks: List[Stripped] = [
        Stripped(
            f"""\
public void visit(IClass that)
{{
{I}that.accept(this);
}}"""
        )
    ]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract void {visit_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        """\
/**
 * Perform double-dispatch to visit the concrete instances.
 */
public abstract class AbstractVisitor implements IVisitor
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_ivisitor_with_context(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the interface for the visitor with context."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
    ]

    blocks: List[Stripped] = []

    # Abstract classes have no particular implementation, so we do not visit
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
void {visit_name}(
{I}{interface_name} that,
{I}ContextT context
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        f"""\
/**
 * Define the interface for a visitor which visits the instances of the model.
 *
 * <p>When you use the visitor, please always call the main dispatching method
 * {{@link IVisitorWithContext#visit}}. You should most probably never call the {{@code visit}}
 * methods directly. They are only made public so that model classes can access them.
 *
 * @param <ContextT> structure of the context
 */
public interface IVisitorWithContext<ContextT>
{{
{I}void visit(IClass that, ContextT context);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_abstract_visitor_with_context(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the visitor with context that performs double-dispatch."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.IVisitorWithContext;"),
    ]

    blocks: List[Stripped] = [
        Stripped(
            f"""\
public void visit(IClass that, ContextT context)
{{
{I}that.accept(this, context);
}}"""
        )
    ]

    # Abstract classes have no particular implementation, so we do not visit
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract void {visit_name}(
{I}{interface_name} that,
{I}ContextT context
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        f"""\
/**
 * Perform double-dispatch to visit the concrete instances
 * with context.
 *
 * @param <ContextT> structure of the context
 */
public abstract class AbstractVisitorWithContext<ContextT>
{I}implements IVisitorWithContext<ContextT>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_itransformer(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the transformer interface."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
    ]

    blocks: List[Stripped] = []

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
T {transform_name}(
{I}{interface_name} that
);"""
            )
        )
    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        f"""\
/**
 * Define the interface for a transformer which transforms recursively
 * the instances into something else.
 *
 * <p>When you use the transformer, please always call the main dispatching method
 * {{@link ITransformer#transform}}. You should most probably never call the {{@code transform}}
 * methods directly. They are only made public so that model classes can access them.
 *
 * @param <T> type of the transformation result
 */
public interface ITransformer<T> {{
{I}T transform(IClass that);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_abstract_transformer(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the most abstract transformer that merely double-dispatches."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.ITransformer;"),
    ]

    blocks: List[Stripped] = [
        Stripped(
            f"""\
public T transform(IClass that)
{{
{I}return that.transform(this);
}}"""
        )
    ]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract T {transform_name}(
{I}{interface_name} that
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        """\
/**
 * Perform double-dispatch to transform recursively
 * the instances into something else.
 *
 * @param <T> type of the transformation result
 */
public abstract class AbstractTransformer<T> implements ITransformer<T>
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_itransformer_with_context(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the interface for the transformer with context."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
    ]

    blocks: List[Stripped] = []

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
T {transform_name}(
{I}{interface_name} that,
{I}ContextT context
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        f"""\
/**
 * Define the interface for a transformer which recursively transforms
 * the instances into something else while the context is passed along.
 *
 * <p>When you use the transformer, please always call the main dispatching method
 * {{@link ITransformerWithContext#transform}}. You should most probably never call the {{@code transform}}
 * methods directly. They are only made public so that model classes can access them.
 *
 * @param <ContextT> structure of the context
 * @param <T> type of the transformation result
 */
public interface ITransformerWithContext<ContextT, T> {{
{I}T transform(IClass that, ContextT context);
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_abstract_transformer_with_context(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Stripped:
    """Generate the most abstract transformer that merely double-dispatches."""
    java_imports: List[Stripped] = [
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.ITransformerWithContext;"),
    ]

    blocks: List[Stripped] = [
        Stripped(
            f"""\
public T transform(IClass that, ContextT context)
{{
{I}return that.transform(this, context);
}}"""
        )
    ]

    # Abstract classes have no particular implementation, so we do not transform
    # them.
    for cls in symbol_table.concrete_classes:
        interface_name = java_naming.interface_name(cls.name)
        transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

        blocks.append(
            Stripped(
                f"""\
public abstract T {transform_name}(
{I}{interface_name} that,
{I}ContextT context
);"""
            )
        )

    writer = io.StringIO()

    for java_import in java_imports:
        writer.write(f"{java_import}\n")

    if len(java_imports) > 0:
        writer.write("\n")

    writer.write(
        f"""\
/**
 * Perform double-dispatch to transform recursively
 * the instances into something else.
 *
 * <p>When you use the transformer, please always call the main dispatching method
 * {{@link AbstractTransformerWithContext#transform}}. You should most probably never call the {{@code transform}}
 * methods directly. They are only made public so that model classes can access them.
 *
 * @param <ContextT> structure of the context
 * @param <T> type of the transformation result
 */
public abstract class AbstractTransformerWithContext<ContextT, T>
{I}implements ITransformerWithContext<ContextT, T>
{{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")
        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue())


def _generate_java_file(
    class_name: Stripped, code: Stripped, package: java_common.PackageIdentifier
) -> java_common.JavaFile:
    file_name = Stripped(f"{class_name}.java")

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.visitation;"),
        code,
        java_common.WARNING,
    ]

    file_code = Stripped("\n\n".join(blocks))

    code_with_eof = f"{file_code}\n"

    return java_common.JavaFile(
        file_name,
        code_with_eof,
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable, package: java_common.PackageIdentifier
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code of visitors to iterate over instances.
    """

    files: List[java_common.JavaFile] = [
        _generate_java_file(
            Stripped("IVisitor"),
            _generate_ivisitor(symbol_table=symbol_table, package=package),
            package,
        ),
        _generate_java_file(
            Stripped("VisitorThrough"),
            _generate_visitor_through(symbol_table=symbol_table, package=package),
            package,
        ),
        _generate_java_file(
            Stripped("AbstractVisitor"),
            _generate_abstract_visitor(symbol_table=symbol_table, package=package),
            package,
        ),
        _generate_java_file(
            Stripped("IVisitorWithContext"),
            _generate_ivisitor_with_context(symbol_table=symbol_table, package=package),
            package,
        ),
        _generate_java_file(
            Stripped("AbstractVisitorWithContext"),
            _generate_abstract_visitor_with_context(
                symbol_table=symbol_table, package=package
            ),
            package,
        ),
        _generate_java_file(
            Stripped("ITransformer"),
            _generate_itransformer(symbol_table=symbol_table, package=package),
            package,
        ),
        _generate_java_file(
            Stripped("AbstractTransformer"),
            _generate_abstract_transformer(symbol_table=symbol_table, package=package),
            package,
        ),
        _generate_java_file(
            Stripped("ITransformerWithContext"),
            _generate_itransformer_with_context(
                symbol_table=symbol_table, package=package
            ),
            package,
        ),
        _generate_java_file(
            Stripped("AbstractTransformerWithContext"),
            _generate_abstract_transformer_with_context(
                symbol_table=symbol_table, package=package
            ),
            package,
        ),
    ]

    return files, None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
