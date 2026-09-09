"""Generate code for copying instances in memory."""

import io
import textwrap
from typing import Tuple, Optional, List

from icontract import ensure

from aas_core_codegen import intermediate, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    indent_but_first_line,
    assert_never,
)
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)


# region Generate


def _generate_shallow_copy_transform_method(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the method in the transformer to make a shallow copy of ``cls''."""
    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
        set(prop.name for prop in cls.properties)
        == set(arg.name for arg in cls.constructor.arguments)
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    cls_name = java_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        return_statement = Stripped(f"return new {cls_name}();")
    else:
        constructor_arg_exprs = []  # type: List[str]
        for arg in cls.constructor.arguments:
            if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                getter_name = java_naming.getter_name(arg.name)
                constructor_arg_exprs.append(f"that.{getter_name}().orElse(null)")
            else:
                getter_name = java_naming.getter_name(arg.name)
                constructor_arg_exprs.append(f"that.{getter_name}()")

        args_joined = ", ".join(constructor_arg_exprs)
        return_statement = Stripped(f"return new {cls_name}({args_joined});")

        if len(return_statement) > 70:
            args_joined = ",\n".join(constructor_arg_exprs)
            return_statement = Stripped(
                f"""\
return new {cls_name}(
{I}{indent_but_first_line(args_joined, I)});"""
            )

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
@Override
public IClass {transform_name}(
{I}{interface_name} that
) {{
{I}{indent_but_first_line(return_statement, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_shallow_copier(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transformer which makes shallow copies."""
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Copying/ShallowCopier/transform_{cls.name}.java"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The snippet for making shallow copies is missing "
                        f"for the implementation-specific "
                        f"class {cls.name}: {implementation_key}",
                    )
                )
                continue

            blocks.append(spec_impls[implementation_key])
        else:
            blocks.append(_generate_shallow_copy_transform_method(cls=cls))

    writer = io.StringIO()
    writer.write(
        """\
/**
 * Dispatch the making of shallow copies.
 */
private static class _ShallowCopier extends AbstractTransformer<IClass> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_deep_copy_transform_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method in the transformer to make a deep copy of ``cls''."""
    property_names = [prop.name for prop in cls.properties]
    constructor_argument_names = [arg.name for arg in cls.constructor.arguments]

    # fmt: off
    assert (
            set(prop.name for prop in cls.properties)
            == set(arg.name for arg in cls.constructor.arguments)
    ), (
        f"Expected the properties to coincide with constructor arguments, "
        f"but they do not for {cls.name!r}:"
        f"{property_names=}, {constructor_argument_names=}"
    )
    # fmt: on

    cls_name = java_naming.class_name(cls.name)

    body_blocks = []  # type: List[Stripped]

    if len(cls.constructor.arguments) == 0:
        body_blocks.append(Stripped(f"return new {cls_name}();"))
    else:
        for arg in cls.constructor.arguments:
            getter_name = java_naming.getter_name(arg.name)
            optional = isinstance(
                arg.type_annotation, intermediate.OptionalTypeAnnotation
            )

            type_anno = intermediate.beneath_optional(arg.type_annotation)

            if isinstance(type_anno, intermediate.TupleTypeAnnotation):
                if not any(
                    isinstance(item, intermediate.OurTypeAnnotation)
                    and isinstance(item.our_type, intermediate.Class)
                    for item in type_anno.items
                ):
                    # NOTE (mristin):
                    # None of the items is a class, so a shallow copy of the tuple
                    # itself already gives us a deep copy, since the tuple record
                    # is immutable and the remaining items (primitives, constrained
                    # primitives, enumeration literals) are immutable as well.
                    continue

                variable_name = java_naming.variable_name(Identifier(f"the_{arg.name}"))
                variable_type = java_common.generate_type(type_anno)

                def _item_expr(
                    source_expr: str,
                    i: int,
                    item_type_anno: intermediate.TypeAnnotationUnion,
                ) -> Stripped:
                    """Generate the expression copying the ``i``-th tuple item."""
                    item_access = f"{source_expr}.item{i + 1}()"
                    if isinstance(
                        item_type_anno, intermediate.OurTypeAnnotation
                    ) and isinstance(item_type_anno.our_type, intermediate.Class):
                        return Stripped(f"deep({item_access})")

                    return Stripped(item_access)

                if not optional:
                    source_expr = f"that.{getter_name}()"
                    tuple_literal = java_common.generate_tuple_literal(
                        item_exprs=[
                            _item_expr(source_expr, i, item_type_anno)
                            for i, item_type_anno in enumerate(type_anno.items)
                        ]
                    )
                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type} {variable_name} = {indent_but_first_line(tuple_literal, I)};"""
                        )
                    )
                else:
                    other_property_name = java_naming.variable_name(
                        Identifier(f"that_{arg.name}")
                    )
                    tuple_literal = java_common.generate_tuple_literal(
                        item_exprs=[
                            _item_expr(other_property_name, i, item_type_anno)
                            for i, item_type_anno in enumerate(type_anno.items)
                        ]
                    )
                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type} {other_property_name} =
{I}that.{getter_name}().orElse(null);
{variable_type} {variable_name} = ({other_property_name} == null)
{I}? null
{I}: {indent_but_first_line(tuple_literal, I)};"""
                        )
                    )

                continue

            if not isinstance(type_anno, intermediate.ListTypeAnnotation):
                continue

            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "We handle only lists of atomic values (primitives, "
                "constrained primitives, enumeration literals) or lists of "
                "classes in the deep copies at the moment. Lists of lists "
                "or lists of optionals are not supported. Please contact "
                "the developers if you need this feature."
            )

            # We need to prefix to avoid any possible naming conflicts.
            variable_name = java_naming.variable_name(Identifier(f"the_{arg.name}"))

            variable_type = java_common.generate_type(type_anno)

            if isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ) and isinstance(type_anno.items.our_type, intermediate.Class):
                inner_type = java_naming.interface_name(type_anno.items.our_type.name)

                if not optional:
                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type} {variable_name} = new ArrayList<>(
{I}that.{getter_name}().size());
for ({inner_type} item : that.{getter_name}()) {{
{I}{variable_name}.add(deep(item));
}}"""
                        )
                    )
                else:
                    other_property_name = java_naming.variable_name(
                        Identifier(f"that_{arg.name}")
                    )

                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type} {other_property_name} =
{I}that.{getter_name}().orElse(null);
{variable_type} {variable_name} = null;
if ({other_property_name} != null) {{
{I}{variable_name} = new ArrayList<>(
{II}{other_property_name}.size());
{I}for ({inner_type} item : {other_property_name})
{I}{{
{II}{variable_name}.add(deep(item));
{I}}}
}}"""
                        )
                    )
            else:
                # NOTE (mristin):
                # The items are atomic values (primitives, constrained
                # primitives or enumeration literals). They are immutable in
                # Java (or, in the case of byte arrays, treated as such
                # elsewhere in this generator), so a shallow copy of the list
                # container itself already gives us a deep copy.
                if not optional:
                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type} {variable_name} = new ArrayList<>(
{I}that.{getter_name}());"""
                        )
                    )
                else:
                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type} {variable_name} = that.{getter_name}().isPresent()
{I}? new ArrayList<>(that.{getter_name}().get())
{I}: null;"""
                        )
                    )

        constructor_arg_exprs = []  # type: List[str]
        for arg in cls.constructor.arguments:
            getter_name = java_naming.getter_name(arg.name)

            type_anno = intermediate.beneath_optional(arg.type_annotation)

            optional = isinstance(
                arg.type_annotation, intermediate.OptionalTypeAnnotation
            )

            if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
                if optional:
                    constructor_arg_exprs.append(
                        f"""that.{getter_name}().orElse(null)"""
                    )
                else:
                    constructor_arg_exprs.append(f"""that.{getter_name}()""")

            elif isinstance(type_anno, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.our_type, intermediate.Enumeration):
                    if optional:
                        constructor_arg_exprs.append(
                            f"""that.{getter_name}().orElse(null)"""
                        )
                    else:
                        constructor_arg_exprs.append(f"""that.{getter_name}()""")

                elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                    if optional:
                        constructor_arg_exprs.append(
                            f"""that.{getter_name}().orElse(null)"""
                        )
                    else:
                        constructor_arg_exprs.append(f"""that.{getter_name}()""")

                elif isinstance(
                    type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    if optional:
                        constructor_arg_exprs.append(
                            f"""that.{getter_name}().orElse(null)"""
                        )
                    else:
                        constructor_arg_exprs.append(f"deep(that.{getter_name}())")
                else:
                    assert_never(type_anno.our_type)

            elif isinstance(type_anno, intermediate.ListTypeAnnotation):
                # See how this variable is computed above in the generated code.
                constructor_arg_exprs.append(
                    java_naming.variable_name(Identifier(f"the_{arg.name}"))
                )
            elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                if any(
                    isinstance(item, intermediate.OurTypeAnnotation)
                    and isinstance(item.our_type, intermediate.Class)
                    for item in type_anno.items
                ):
                    # See how this variable is computed above in the generated code.
                    constructor_arg_exprs.append(
                        java_naming.variable_name(Identifier(f"the_{arg.name}"))
                    )
                elif optional:
                    constructor_arg_exprs.append(
                        f"""that.{getter_name}().orElse(null)"""
                    )
                else:
                    constructor_arg_exprs.append(f"""that.{getter_name}()""")
            else:
                assert_never(type_anno)

        return_statement_writer = io.StringIO()

        return_statement_writer.write(f"return new {cls_name}(\n")

        for i, arg_expr in enumerate(constructor_arg_exprs):
            return_statement_writer.write(textwrap.indent(arg_expr, I))

            if i < len(constructor_arg_exprs) - 1:
                return_statement_writer.write(",\n")
            else:
                return_statement_writer.write("\n")

        return_statement_writer.write(");")

        body_blocks.append(Stripped(return_statement_writer.getvalue()))

    body_writer = io.StringIO()
    for i, body_block in enumerate(body_blocks):
        if i > 0:
            body_writer.write("\n\n")

        body_writer.write(body_block)

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
@Override
public IClass {transform_name} (
{I}{interface_name} that
) {{
{I}{indent_but_first_line(body_writer.getvalue(), I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_deep_copier(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transformer which makes deep copies."""
    errors = []  # type: List[Error]

    blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Copying/DeepCopier/transform_{cls.name}.java"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"This snippet for making deep copies is missing "
                        f"for the implementation-specific "
                        f"class {cls.name}: {implementation_key}",
                    )
                )
                continue

            blocks.append(spec_impls[implementation_key])
        else:
            blocks.append(_generate_deep_copy_transform_method(cls=cls))

    writer = io.StringIO()
    writer.write(
        """\
/** Dispatch the making of deep copies. */
private static class _DeepCopier extends AbstractTransformer<IClass> {
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code for copying instances in memory.
    """
    errors = []  # type: List[Error]

    imports = [
        Stripped("import java.util.List;"),
        Stripped("import java.util.ArrayList;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.types.{java_common.INTERFACE_PKG}.IClass;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.impl.*;"),
        Stripped(f"import {package}.types.model.*;"),
    ]  # type: List[Stripped]

    # NOTE (empwilli):
    # We wrap the shallow and deep copying in generic methods to allow for easier
    # enforcement of runtime type safety for the client. Otherwise, if we directly
    # provided the transformer, the client would always need to make the casts, which
    # is cumbersome.

    copy_blocks = [
        Stripped(
            """private static final _ShallowCopier shallowCopierInstance = new _ShallowCopier();"""
        ),
        Stripped(
            """private static final _DeepCopier deepCopierInstance = new _DeepCopier();"""
        ),
        Stripped(
            f"""\
/**
 * Make a shallow copy of {{@code that}}.
 *
 * <p>All the properties are copied by reference. This includes also the lists.
 * Hence, a list property is copied by reference, and not, as sometimes might be
 * expected, as a new list of underlying references.
 *
 * @param that to be copied in a shallow manner
 */
@SuppressWarnings("unchecked")
public static <T extends IClass> T shallow(T that) {{
{I}return (T) shallowCopierInstance.transform(that);
}}"""
        ),
        Stripped(
            f"""\
/**
 * Make a recursively a deep copy of {{@code that}}.
 *
 * @param that to be deeply copied in a recursive manner
 */
@SuppressWarnings("unchecked")
public static <T extends IClass> T deep(T that) {{
{I}return (T) deepCopierInstance.transform(that);
}}"""
        ),
    ]  # type: List[Stripped]

    shallow_copier_block, shallow_errors = _generate_shallow_copier(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if shallow_errors is not None:
        errors.extend(shallow_errors)
    else:
        assert shallow_copier_block is not None
        copy_blocks.append(shallow_copier_block)

    deep_copier_block, deep_errors = _generate_deep_copier(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
    if deep_errors is not None:
        errors.extend(deep_errors)
    else:
        assert deep_copier_block is not None
        copy_blocks.append(deep_copier_block)

    if len(errors) > 0:
        return None, errors

    copying_writer = io.StringIO()
    copying_writer.write(
        """\
/**
 * Allow for making shallow and deep copies of AAS model instances.
 */
public class Copying
{
"""
    )

    for i, copy_block in enumerate(copy_blocks):
        if i > 0:
            copying_writer.write("\n\n")

        copying_writer.write(textwrap.indent(copy_block, I))

    copying_writer.write("\n}")

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.copying;"),
        Stripped("\n".join(imports)),
        Stripped(f"{copying_writer.getvalue()}"),
        java_common.WARNING,
    ]  # type: List[Stripped]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return [java_common.JavaFile("Copying.java", writer.getvalue())], None


# endregion


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
