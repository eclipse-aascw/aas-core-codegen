"""Generate code for enhancing model classes."""

import io
import textwrap
from typing import Tuple, Optional, List, Mapping, Set

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Identifier,
    assert_never,
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.java import (
    common as java_common,
    naming as java_naming,
)
from aas_core_codegen.java.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


def _generate_delegate_method(method: intermediate.Method) -> Stripped:
    """Generate the delegated method to ``instance``."""
    returns = (
        java_common.generate_type(method.returns)
        if method.returns is not None
        else "void"
    )

    arg_types_names = [
        (
            java_common.generate_type(arg.type_annotation),
            java_naming.argument_name(arg.name),
        )
        for arg in method.arguments
    ]

    method_name = java_naming.method_name(method.name)

    return_prefix = "return " if method.returns is not None else ""

    if len(method.arguments) == 0:
        return Stripped(
            f"""\
public {returns} {method_name}() {{
{I}{return_prefix}instance.{method_name}();
}}"""
        )

    arguments_definition = ",\n".join(
        f"{arg_type} {arg_name}" for arg_type, arg_name in arg_types_names
    )

    arguments_delegation = ",\n".join(arg_name for _, arg_name in arg_types_names)

    return Stripped(
        f"""\
public {returns} {method_name}(
{I}{indent_but_first_line(arguments_definition, I)}
)
{{
{I}{return_prefix}instance.{method_name}(
{II}{indent_but_first_line(arguments_delegation, II)}
{I});
}}"""
    )


def _generate_enhanced_abstract_class(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    enhanced = Stripped(
        f"""\
public abstract class Enhanced<EnhancementT> {{
{I}protected final EnhancementT enhancement;

{I}protected Enhanced(EnhancementT enhancement) {{
{II}this.enhancement = enhancement;
{I}}}

{I}EnhancementT getEnhancement() {{
{II}return enhancement;
{I}}}
}}"""
    )

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.enhancing;"),
        enhanced,
        java_common.WARNING,
    ]

    code = "\n\n".join(blocks)

    return java_common.JavaFile(
        "Enhanced.java",
        f"{code}\n",
    )


def _generate_unwrapper_class(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    imports: List[Stripped] = [
        Stripped("import java.util.Optional;"),
        Stripped(f"import {package}.types.model.*;"),
    ]

    unwrapper = Stripped(
        f"""\
/**
 * Unwrap enhancements from the wrapped instances.
 *
 * @param <EnhancementT> structure of the expected enhancement
 */
public class Unwrapper<EnhancementT> {{
{I}/**
{I} * Unwrap the given model instance.
{I} *
{I} * @param that model instance to be unwrapped
{I} * @return Enhancement, or {{@link java.util.Optional#empty()}} if {{@code that}}
{I} * has not been wrapped yet.
{I} */
{I}public Optional<EnhancementT> unwrap(IClass that)
{I}{{
{II}if (that instanceof Enhanced) {{
{III}@SuppressWarnings("unchecked")
{III}Enhanced<EnhancementT> enhanced = (Enhanced<EnhancementT>) that;
{III}return Optional.of(enhanced.getEnhancement());
{II}}} else {{
{III}return Optional.empty();
{II}}}
{I}}}

{I}/**
{I} * Unwrap the given model instance.
{I} *
{I} * @param that model instance to be unwrapped
{I} * @return Enhancement wrapped around {{@code that}}
{I} */
{I}public EnhancementT mustUnwrap(IClass that)
{I}{{
{II}Optional<EnhancementT> value = unwrap(that);
{II}if (!value.isPresent()) {{
{III}throw new IllegalArgumentException(
{IIII}"Expected the instance to have been wrapped, but it was not: " + that
{III});
{II}}}
{II}return value.get();
{I}}}
}}"""
    )

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.enhancing;"),
        Stripped("\n".join(imports)),
        unwrapper,
        java_common.WARNING,
    ]

    code = "\n\n".join(blocks)

    return java_common.JavaFile(
        "Unwrapper.java",
        f"{code}\n",
    )


def _generate_enhancer_class(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    imports: List[Stripped] = [
        Stripped("import java.util.function.Function;"),
        Stripped("import java.util.Optional;"),
        Stripped(f"import {package}.enhancing.Unwrapper;"),
        Stripped(f"import {package}.types.model.*;"),
    ]

    enhancer = Stripped(
        f"""\
/**
 * Wrap and unwrap the instances of model classes with enhancement.
 *
 * @param <EnhancementT> structure of the enhancement
 */
public class Enhancer<EnhancementT> extends Unwrapper<EnhancementT> {{
{I}private final _Wrapper<EnhancementT> wrapper;

{I}/**
{I} * @param enhancementFactory how to enhance the instances.
{I} *
{I} * <p>If it returns {{@code null}}, the instance will not be wrapped. However,
{I} * the wrapping will continue recursively.
{I} */
{I}public Enhancer(
{II}Function<IClass, Optional<EnhancementT>> enhancementFactory
{I}) {{
{II}this.wrapper = new _Wrapper<>(enhancementFactory);
{I}}}

{I}/**
{I} * Wrap the instance with an enhancement.
{I} *
{I} * <p>Double wraps are not allowed to prevent runtime leakage.
{I} *
{I} * <p>If you use references to the instance objects, you have to update them
{I} * after the wrapping, as the wrapping is recursive.
{I} *
{I} * @param that model instance to be wrapped
{I} * @return {{@code that}} instance wrapped recursively with enhancements
{I} */
{I}public IClass wrap(
{II}IClass that
{I}) {{
{II}IClass wrapped;
{II}try {{
{III}wrapped = wrapper.transform(that);
{II}}} catch (IllegalArgumentException exception) {{
{III}throw new UnsupportedOperationException(
{IIII}"Expected the wrapped instance to be an instance of IClass, " +
{IIII}"but got: " + that
{III});
{II}}}

{II}return wrapped;
{I}}}
}}"""
    )

    blocks: List[Stripped] = [
        java_common.WARNING,
        Stripped(f"package {package}.enhancing;"),
        Stripped("\n".join(imports)),
        enhancer,
        java_common.WARNING,
    ]

    code = "\n\n".join(blocks)

    return java_common.JavaFile(
        "Enhancer.java",
        f"{code}\n",
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_enhanced_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
# fmt: on
    """Generate the structure for the enhanced concrete class."""
    enhanced_name = java_naming.class_name(Identifier(f"enhanced_{cls.name}"))
    interface_name = java_naming.interface_name(cls.name)

    blocks: List[Stripped] = [
        Stripped(f"private final {interface_name} instance;"),
        Stripped(
            f"""\
public {enhanced_name}(
{I}{interface_name} instance,
{I}EnhancementT enhancement
) {{
{I}super(enhancement);
{I}this.instance = instance;
}}"""
        ),
    ]

    for prop in cls.properties:
        prop_type = java_common.generate_type(prop.type_annotation)

        inner_type = java_common.generate_type(
            intermediate.beneath_optional(prop.type_annotation)
        )

        prop_name = java_naming.property_name(prop.name)

        getter_name = java_naming.getter_name(prop.name)

        setter_name = java_naming.setter_name(prop.name)

        if isinstance(prop_type, intermediate.OptionalTypeAnnotation):
            blocks.append(
                Stripped(
                    f"""\
@Override
public {prop_type} {getter_name}() {{
{I}return instance.{getter_name}();
}}"""
                )
            )
        else:
            blocks.append(
                Stripped(
                    f"""\
@Override
public {prop_type} {getter_name}() {{
{I}return instance.{getter_name}();
}}"""
                )
            )

        blocks.append(
            Stripped(
                f"""\
@Override
public void {setter_name}({inner_type} {prop_name}) {{
{I}instance.{setter_name}({prop_name});
}}"""
            )
        )

    # region OverXOrEmpty getter

    for prop in cls.properties:
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(
            prop.type_annotation.value,
            (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation),
        ):
            prop_name = java_naming.property_name(prop.name)
            method_name = f"over{java_naming.class_name(prop.name)}OrEmpty"
            getter_name = java_naming.getter_name(prop.name)
            items_type = java_common.generate_type(prop.type_annotation.value.items)

            blocks.append(
                Stripped(
                    f"""\
public Iterable<{items_type}> {method_name}() {{
{I}return instance.{method_name}();
}}"""
                )
            )

    # endregion

    for method in cls.methods:
        if method.visibility is not intermediate.Visibility.PUBLIC:
            continue

        blocks.append(_generate_delegate_method(method))

    visit_name = java_naming.method_name(Identifier(f"visit_{cls.name}"))

    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks.extend(
        [
            Stripped(
                f"""\
public Iterable<IClass> descendOnce() {{
{I}return instance.descendOnce();
}}"""
            ),
            Stripped(
                f"""\
public Iterable<IClass> descend() {{
{I}return instance.descend();
}}"""
            ),
            Stripped(
                f"""\
public void accept(IVisitor visitor) {{
{I}visitor.{visit_name}(instance);
}}"""
            ),
            Stripped(
                f"""\
public <ContextT> void accept(
{I}IVisitorWithContext<ContextT> visitor,
{I}ContextT context
) {{
{I}visitor.{visit_name}(instance, context);
}}"""
            ),
            Stripped(
                f"""\
public <T> T transform(ITransformer<T> transformer) {{
{I}return transformer.{transform_name}(instance);
}}"""
            ),
            Stripped(
                f"""\
public <ContextT, T> T transform(
{I}ITransformerWithContext<ContextT, T> transformer,
{I}ContextT context
) {{
{I}return transformer.{transform_name}(instance, context);
}}"""
            ),
        ]
    )

    writer = io.StringIO()
    writer.write(
        f"""\
public class {enhanced_name}<EnhancementT>
{I}extends Enhanced<EnhancementT>
{I}implements {interface_name} {{
"""
    )

    if len(blocks) > 0:
        for i, block in enumerate(blocks):
            if i > 0:
                writer.write("\n\n")
            writer.write(textwrap.indent(block, I))
    else:
        writer.write("// No properties to wire to instance.")

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _generate_enhanced(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    files: List[java_common.JavaFile] = []

    errors: List[Error] = []

    for cls in symbol_table.concrete_classes:
        cls_name = java_naming.class_name(cls.name)

        code, error = _generate_enhanced_class(cls=cls)
        if error is not None:
            errors.append(error)
            continue

        assert code is not None

        imports: List[Stripped] = [
            Stripped("import java.lang.Iterable;"),
            Stripped("import java.util.Optional;"),
            Stripped("import java.util.List;"),
            Stripped(f"import {package}.common.*;"),
            Stripped(f"import {package}.visitation.IVisitor;"),
            Stripped(f"import {package}.visitation.IVisitorWithContext;"),
            Stripped(f"import {package}.visitation.ITransformer;"),
            Stripped(f"import {package}.visitation.ITransformerWithContext;"),
            Stripped(f"import {package}.types.enums.*;"),
            Stripped(f"import {package}.types.impl.*;"),
            Stripped(f"import {package}.types.model.*;"),
        ]

        imports.extend(
            Stripped(f"import {json_import};")
            for json_import in java_common.json_imports_if_necessary(
                prop.type_annotation for prop in cls.properties
            )
        )

        imports.extend(
            Stripped(f"import {set_import};")
            for set_import in java_common.set_imports_if_necessary(
                cls, with_bodies=False
            )
        )

        blocks: List[Stripped] = [
            java_common.WARNING,
            Stripped(f"package {package}.enhancing;"),
            Stripped("\n".join(imports)),
            code,
            java_common.WARNING,
        ]

        code = Stripped("\n\n".join(blocks))

        files.append(
            java_common.JavaFile(
                f"Enhanced{cls_name}.java",
                f"{code}\n",
            ),
        )
    if len(errors) > 0:
        return None, errors

    return files, None


def _generate_wrap_helpers(with_union: bool) -> List[Stripped]:
    """
    Generate the ``wrap`` overloads for an instance and, if needed, a named union.

    A transformation gives back an ``IClass``, so the ``wrap`` of an instance casts
    it back to the caller's own type. The cast is unchecked as the type is erased,
    but the compiler checks it on the call site, where the type is known.

    A named union is not itself an ``IClass``, so it can not be dispatched by
    the inherited, ``IClass``-typed ``transform``, and its underlying instance
    has to be unwrapped, enhanced and wrapped back up. ``T`` is bounded by
    ``IUnion<T>`` (see ``_generate_iunion`` in ``_generate_types.py``) instead of
    by the union's own type, so we need only this one overload for *all* named
    unions, while ``T.withUnderlying(...)`` still lets the result come back as
    the caller's own concrete union type.
    """
    helpers: List[Stripped] = [
        Stripped(
            f"""\
@SuppressWarnings("unchecked")
private <T extends IClass> T wrap(T that) {{
{I}return (T) transform(that);
}}"""
        )
    ]

    if with_union:
        helpers.append(
            Stripped(
                f"""\
private <T extends IUnion<T>> T wrap(T that) {{
{I}return that.withUnderlying(
{II}wrap(that.getUnderlying()));
}}"""
            )
        )

    return helpers


def _wrap_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of ``_Wrapper`` wrapping the instances held by ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.java.common.type_moniker`), so two different
    containers never share a method. The moniker contains an underscore, so
    the name never collides with ``wrap``.
    """
    return Identifier(f"wrap{java_common.type_moniker(type_anno)}")


@require(lambda type_anno, descendability: type_anno in descendability)
def _generate_wrap_expr(
    expr: str,
    type_anno: intermediate.TypeAnnotationUnion,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the expression wrapping the instances held by the value at ``expr``.

    A container is delegated to its method in ``_Wrapper``, which wraps only one
    level and calls the method of its items by name. This way the wrapping is
    composed of plain functions, to any depth.

    A value which holds no instances is given back as-is.
    """
    if not descendability[type_anno]:
        return Stripped(expr)

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # A named union has its own ``wrap`` overload (see
        # :py:func:`_generate_wrap_helpers`), so it is wrapped exactly like
        # a class instance.
        return Stripped(f"wrap({expr})")

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        return Stripped(f"{_wrap_container_name(type_anno)}({expr})")

    raise AssertionError(
        f"Unexpected type annotation holding instances: {type_anno}. "
        f"The optionals nested in the containers should have been refused in "
        f"parse._translate._verify_symbol_table."
    )


@require(
    lambda type_anno, descendability: (
        type_anno in descendability and descendability[type_anno]
    )
)
def _generate_wrap_container(
    type_anno: intermediate.ContainerTypeAnnotation,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the method of ``_Wrapper`` wrapping the instances held by ``type_anno``.

    The ``descendability`` maps ``type_anno`` and its nested type annotations,
    see :py:func:`aas_core_codegen.intermediate.map_descendability`.
    """
    value_type = java_common.generate_type(type_anno)

    body: Stripped
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        container_class = (
            "ArrayList"
            if isinstance(type_anno, intermediate.ListTypeAnnotation)
            else "HashSet"
        )
        item_type = java_common.generate_type(type_anno.items)
        item_wrap = _generate_wrap_expr("item", type_anno.items, descendability)

        body = Stripped(
            f"""\
{value_type} result = new {container_class}<>(that.size());
for ({item_type} item : that) {{
{I}result.add({indent_but_first_line(item_wrap, I)});
}}
return result;"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        tuple_literal = java_common.generate_tuple_literal(
            item_exprs=[
                _generate_wrap_expr(
                    f"that.item{i + 1}()", item_type_anno, descendability
                )
                for i, item_type_anno in enumerate(type_anno.items)
            ]
        )

        body = Stripped(f"return {tuple_literal};")

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
/**
 * Wrap the instances held by {{@code that}} recursively in a new container.
 */
private {value_type} {_wrap_container_name(type_anno)}(
{I}{indent_but_first_line(value_type, I)} that) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_transform(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method to wrap the instance with an enhancement."""
    blocks: List[Stripped] = [
        Stripped(
            f"""\
if (that instanceof Enhanced)
{{
{I}throw new IllegalArgumentException(
{II}"The instance has been already enhanced: " + that
{I});
}}"""
        )
    ]

    for prop in cls.properties:
        descendability = intermediate.map_descendability(prop.type_annotation)
        if not descendability[prop.type_annotation]:
            continue

        getter_name = java_naming.getter_name(prop.name)
        setter_name = java_naming.setter_name(prop.name)

        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

        value_wrap = _generate_wrap_expr(
            f"that.{getter_name}().get()" if optional else f"that.{getter_name}()",
            intermediate.beneath_optional(prop.type_annotation),
            descendability,
        )

        stmt = Stripped(f"that.{setter_name}({value_wrap});")
        # Heuristic to break the lines, very rudimentary
        if len(stmt) > 70:
            stmt = Stripped(
                f"""\
that.{setter_name}(
{I}{indent_but_first_line(value_wrap, I)});"""
            )

        if optional:
            stmt = Stripped(
                f"""\
if (that.{getter_name}().isPresent()) {{
{I}{indent_but_first_line(stmt, I)}
}}"""
            )

        blocks.append(stmt)

    enhanced_name = java_naming.class_name(Identifier(f"enhanced_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
Optional<EnhancementT> enhancement = enhancementFactory.apply(that);
return !enhancement.isPresent()
{I}? that
{I}: new {enhanced_name}<>(
{II}that,
{II}enhancement.get()
{I});"""
        )
    )

    interface_name = java_naming.interface_name(cls.name)
    transform_name = java_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks_joined = "\n\n".join(blocks)

    return Stripped(
        f"""\
@Override
public IClass {transform_name}(
{I}{interface_name} that
) {{
{I}{indent_but_first_line(blocks_joined, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_wrapper(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[java_common.JavaFile], Optional[List[Error]]]:
    """Generate the transformer that wraps an instance with the enhancement."""
    imports: List[Stripped] = [
        Stripped("import java.util.ArrayList;"),
        Stripped("import java.util.List;"),
        Stripped("import java.util.Optional;"),
        Stripped("import java.util.function.Function;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
    ]

    if intermediate_uses.json_types(symbol_table):
        imports.extend(
            Stripped(f"import {json_import};")
            for json_import in java_common.JSON_IMPORTS
        )

    body: List[Stripped] = [
        Stripped(
            "private final Function<IClass, Optional<EnhancementT>> "
            "enhancementFactory;"
        ),
        Stripped(
            f"""\
_Wrapper(
{I}Function<IClass, Optional<EnhancementT>> enhancementFactory
) {{
{I}this.enhancementFactory = enhancementFactory;
}}"""
        ),
    ]

    for cls in symbol_table.concrete_classes:
        body.append(_generate_transform(cls=cls))

    body.extend(_generate_wrap_helpers(with_union=len(symbol_table.named_unions) > 0))

    # NOTE (mristin):
    # We wrap the instances held by the containers through methods of their own,
    # one per type moniker.
    observed_monikers: Set[str] = set()
    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            descendability = intermediate.map_descendability(prop.type_annotation)

            for type_anno, descendable in descendability.items():
                if not descendable or not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ):
                    continue

                moniker = java_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                if isinstance(type_anno, intermediate.SetTypeAnnotation):
                    imports.append(Stripped("import java.util.HashSet;"))

                # NOTE (mristin):
                # The method spells out the type of the container, so we need to
                # import the sets nested in it as well.
                if Stripped("import java.util.Set;") not in imports and any(
                    isinstance(nested, intermediate.SetTypeAnnotation)
                    for nested in intermediate.over_type_annotation_and_nested_type_annotations(
                        type_anno
                    )
                ):
                    imports.append(Stripped("import java.util.Set;"))

                body.append(
                    _generate_wrap_container(
                        type_anno=type_anno, descendability=descendability
                    )
                )

    writer = io.StringIO()
    writer.write(
        """\
class _Wrapper<EnhancementT> extends AbstractTransformer<IClass> {
"""
    )

    for i, block in enumerate(body):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}")

    blocks: List[Stripped] = [
        Stripped(java_common.WARNING),
        Stripped(Stripped(f"package {package}.enhancing;")),
        Stripped("\n".join(imports)),
        Stripped(writer.getvalue()),
        Stripped(java_common.WARNING),
    ]

    code = Stripped("\n\n".join(blocks))

    return (
        java_common.JavaFile(
            "_Wrapper.java",
            f"{code}\n",
        ),
        None,
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    package: java_common.PackageIdentifier,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code for enhancing model classes.
    """

    errors: List[Error] = []

    java_files: List[java_common.JavaFile] = [
        _generate_enhanced_abstract_class(package),
        _generate_unwrapper_class(package),
        _generate_enhancer_class(package),
    ]

    enhanced_files, enhanced_errors = _generate_enhanced(symbol_table, package)

    if enhanced_errors is not None:
        errors.extend(enhanced_errors)
    else:
        assert enhanced_files is not None

        java_files.extend(enhanced_files)

    wrapper_file, wrapper_errors = _generate_wrapper(symbol_table, package)

    if wrapper_errors is not None:
        errors.extend(wrapper_errors)
    else:
        assert wrapper_file is not None

        java_files.append(wrapper_file)

    if len(errors) > 0:
        return None, errors

    return java_files, None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
