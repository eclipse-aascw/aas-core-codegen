"""Generate code for enhancing model classes."""

import io
import textwrap
from typing import Tuple, Optional, List, Mapping, Set

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.csharp import common as csharp_common, naming as csharp_naming
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)
from aas_core_codegen.intermediate import uses as intermediate_uses


def _generate_delegate_method(method: intermediate.Method) -> Stripped:
    """Generate the delegated method to ``_instance``."""
    returns = (
        csharp_common.generate_type(method.returns, our_type_qualifier=Stripped("Our"))
        if method.returns is not None
        else "void"
    )

    arg_types_names = [
        (
            csharp_common.generate_type(
                arg.type_annotation, our_type_qualifier=Stripped("Our")
            ),
            csharp_naming.argument_name(arg.name),
        )
        for arg in method.arguments
    ]

    method_name = csharp_naming.method_name(method.name)

    return_prefix = "return " if method.returns is not None else ""

    if len(method.arguments) == 0:
        return Stripped(
            f"""\
public {returns} {method_name}()
{{
{I}{return_prefix}_instance.{method_name}();
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
{I}{return_prefix}_instance.{method_name}(
{II}{indent_but_first_line(arguments_delegation, II)}
{I});
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_enhanced_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the structure for the enhanced concrete class."""
    enhanced_name = csharp_naming.class_name(Identifier(f"enhanced_{cls.name}"))
    interface_name = csharp_naming.interface_name(cls.name)

    blocks: List[Stripped] = [
        Stripped(f"private readonly Our.{interface_name} _instance;"),
        Stripped(
            f"""\
public {enhanced_name}(
{I}Our.{interface_name} instance,
{I}TEnhancement enhancement
) : base(enhancement)
{{
{I}_instance = instance;
}}"""
        ),
    ]

    for prop in cls.properties:
        prop_type = csharp_common.generate_type(prop.type_annotation)
        prop_name = csharp_naming.property_name(prop.name)

        blocks.append(
            Stripped(
                f"""\
public {prop_type} {prop_name}
{{
{I}get => _instance.{prop_name};
{I}set => _instance.{prop_name} = value;
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
            prop_name = csharp_naming.property_name(prop.name)
            items_type = csharp_common.generate_type(
                prop.type_annotation.value.items, our_type_qualifier=Stripped("Our")
            )

            blocks.append(
                Stripped(
                    f"""\
public IEnumerable<{items_type}> Over{prop_name}OrEmpty()
{{
{I}return _instance.Over{prop_name}OrEmpty();
}}"""
                )
            )

    # endregion

    for method in cls.methods:
        if method.visibility is not intermediate.Visibility.PUBLIC:
            continue

        blocks.append(_generate_delegate_method(method))

    visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks.extend(
        [
            Stripped(
                f"""\
public IEnumerable<Our.IClass> DescendOnce()
{{
{I}return _instance.DescendOnce();
}}"""
            ),
            Stripped(
                f"""\
public IEnumerable<Our.IClass> Descend()
{{
{I}return _instance.Descend();
}}"""
            ),
            Stripped(
                f"""\
public void Accept(Our.Visitation.IVisitor visitor)
{{
{I}visitor.{visit_name}(_instance);
}}"""
            ),
            Stripped(
                f"""\
public void Accept<TContext>(
{I}Visitation.IVisitorWithContext<TContext> visitor,
{I}TContext context
)
{{
{I}visitor.{visit_name}(_instance, context);
}}"""
            ),
            Stripped(
                f"""\
public T Transform<T>(Visitation.ITransformer<T> transformer)
{{
{I}return transformer.{transform_name}(_instance);
}}"""
            ),
            Stripped(
                f"""\
public T Transform<TContext, T>(
{I}Visitation.ITransformerWithContext<TContext, T> transformer,
{I}TContext context
)
{{
{I}return transformer.{transform_name}(_instance, context);
}}"""
            ),
        ]
    )

    writer = io.StringIO()
    writer.write(
        f"""\
public class {enhanced_name}<TEnhancement>
{I}: Enhanced<TEnhancement>, Our.{interface_name}
{I}where TEnhancement : class
{{
"""
    )

    if len(blocks) > 0:
        for i, block in enumerate(blocks):
            if i > 0:
                writer.write("\n\n")
            writer.write(textwrap.indent(block, I))
    else:
        writer.write("// No properties to wire to _instance.")

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


def _generate_union_wrap_helper() -> Stripped:
    """
    Generate a single ``Wrap`` overload shared by every named union.

    A named union is not itself an ``Our.IClass``, so it can not be passed
    to the generic ``Wrap<T>() where T : Our.IClass``. We add this second
    generic overload, next to it, so that call sites can keep calling
    ``Wrap`` directly, regardless of whether the value at hand is a class
    instance or a named union.

    ``T`` is bounded by ``Our.IUnion<T>`` (see ``generate()`` in
    ``_generate_types.py``) instead of by the union's own type, so we need
    only this one overload for *all* named unions, not one per union --
    while ``T.WithUnderlying(...)`` still lets the result come back as the
    caller's own concrete union type, with no downcast needed at the call site.

    .. note::

        The parameter is typed as ``Our.IUnion<T>``, not bare ``T``, since C#
        does not allow overloading a generic method solely by its type
        parameter's constraint (CS0111), see
        :py:func:`_generate_union_deep_copy_helper` in ``_generate_copying.py``.
    """
    return Stripped(
        f"""\
private T Wrap<T>(Our.IUnion<T> that) where T : Our.IUnion<T>
{{
{I}return that.WithUnderlying(
{II}Transform(that.Underlying));
}}"""
    )


def _wrap_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the method of the ``Wrapper`` wrapping the instances held by ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.csharp.common.type_moniker`), so two different
    containers never share a method.
    """
    return Identifier(f"Wrap_{csharp_common.type_moniker(type_anno)}")


@require(
    lambda type_anno, descendability: (
        type_anno in descendability and descendability[type_anno]
    )
)
def _generate_wrap_expr(
    expr: str,
    type_anno: intermediate.TypeAnnotationUnion,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the expression wrapping the instances held by the value at ``expr``.

    An instance is wrapped by the generic ``Wrap``. A container is delegated to
    its method in the ``Wrapper``, which wraps only one level and calls
    the methods of its items by name. This way the wrapping is composed of
    plain functions, to any depth.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        # NOTE (mristin):
        # A named union has its own ``Wrap`` overload (see
        # :py:func:`_generate_union_wrap_helper`), so it can be wrapped exactly
        # like a class instance.
        return Stripped(f"Wrap({expr})")

    if isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        name = _wrap_container_name(type_anno)

        # Heuristic to break the lines, very rudimentary
        if len(name) + len(expr) > 50:
            return Stripped(
                f"""\
{name}(
{I}{expr})"""
            )

        return Stripped(f"{name}({expr})")

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
    Generate the method of the ``Wrapper`` for ``type_anno``.

    The ``descendability`` maps ``type_anno`` and its nested type annotations,
    see :py:func:`aas_core_codegen.intermediate.map_descendability`.
    """
    value_type = csharp_common.generate_type(
        type_anno, our_type_qualifier=Stripped("Our")
    )

    body: Stripped
    if isinstance(
        type_anno, (intermediate.ListTypeAnnotation, intermediate.SetTypeAnnotation)
    ):
        item_wrap_expr = _generate_wrap_expr(
            expr="item", type_anno=type_anno.items, descendability=descendability
        )

        body = Stripped(
            f"""\
var result = new {value_type}(that.Count);
foreach (var item in that)
{{
{I}result.Add({item_wrap_expr});
}}

return result;"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        tuple_literal = csharp_common.generate_tuple_literal(
            [
                (
                    _generate_wrap_expr(
                        expr=f"that.Item{i + 1}",
                        type_anno=item,
                        descendability=descendability,
                    )
                    if descendability[item]
                    else Stripped(f"that.Item{i + 1}")
                )
                for i, item in enumerate(type_anno.items)
            ]
        )

        body = Stripped(f"return {tuple_literal};")

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
/// <summary>
/// Wrap recursively the instances held by <paramref name="that" />.
/// </summary>
private {value_type} {_wrap_container_name(type_anno)}(
{I}{value_type} that)
{{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_transform(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method to wrap the instance with an enhancement."""
    blocks: List[Stripped] = [
        Stripped(
            f"""\
if (that is Enhanced<TEnhancement>)
{{
{I}throw new System.ArgumentException(
{II}$"The instance has been already enhanced: {{that}}"
{I});
}}"""
        )
    ]

    for prop in cls.properties:
        descendability = intermediate.map_descendability(prop.type_annotation)

        if not descendability[prop.type_annotation]:
            # We can not enhance anything held by this property; nothing to do here.
            continue

        type_anno = intermediate.beneath_optional(prop.type_annotation)
        prop_name = csharp_naming.property_name(prop.name)

        # NOTE (mristin):
        # An optional of a value type, such as a tuple, is a ``System.Nullable``
        # which has to be unwrapped. The assignment back needs no wrapping as
        # the value is implicitly converted.
        access_expr = f"that.{prop_name}"
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and csharp_common.is_value_type(type_anno):
            access_expr = f"that.{prop_name}.Value"

        wrap_expr = _generate_wrap_expr(
            expr=access_expr, type_anno=type_anno, descendability=descendability
        )

        wrap_stmt = Stripped(f"that.{prop_name} = {wrap_expr};")

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            condition = (
                f"that.{prop_name}.HasValue"
                if csharp_common.is_value_type(type_anno)
                else f"that.{prop_name} != null"
            )

            wrap_stmt = Stripped(
                f"""\
if ({condition})
{{
{I}{indent_but_first_line(wrap_stmt, I)}
}}"""
            )

        blocks.append(wrap_stmt)

    enhanced_name = csharp_naming.class_name(Identifier(f"enhanced_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
var enhancement = _enhancementFactory(that);
return (enhancement == null)
{I}? that
{I}: new {enhanced_name}<TEnhancement>(
{II}that,
{II}enhancement
{I});"""
        )
    )

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks_joined = "\n\n".join(blocks)

    return Stripped(
        f"""\
public override Our.IClass {transform_name}(
{I}Our.{interface_name} that
)
{{
{I}{indent_but_first_line(blocks_joined, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_wrapper(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transformer that wraps an instance with the enhancement."""
    blocks: List[Stripped] = [
        Stripped(
            "private readonly System.Func<Our.IClass, TEnhancement?> "
            "_enhancementFactory;"
        ),
        Stripped(
            f"""\
internal Wrapper(
{I}System.Func<Our.IClass, TEnhancement?> enhancementFactory
)
{{
{I}_enhancementFactory = enhancementFactory;
}}"""
        ),
    ]

    for cls in symbol_table.concrete_classes:
        blocks.append(_generate_transform(cls=cls))

    container_blocks: List[Stripped] = []
    wraps_classes = False

    observed_monikers: Set[str] = set()
    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            descendability = intermediate.map_descendability(prop.type_annotation)

            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
                    type_anno.our_type, intermediate.Class
                ):
                    wraps_classes = True
                    continue

                if (
                    not isinstance(
                        type_anno, intermediate.ContainerTypeAnnotationAsTuple
                    )
                    or not descendability[type_anno]
                ):
                    continue

                moniker = csharp_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                container_blocks.append(
                    _generate_wrap_container(
                        type_anno=type_anno, descendability=descendability
                    )
                )

    if wraps_classes:
        blocks.append(
            Stripped(
                f"""\
/// <summary>
/// Wrap recursively <paramref name="that" /> and keep its static type.
/// </summary>
private T Wrap<T>(T that) where T : Our.IClass
{{
{I}var transformed = Transform(that);
{I}return (transformed is T casted)
{II}? casted
{II}: throw new System.InvalidOperationException(
{III}$"Expected the transformed value to be a {{typeof(T).Name}}, " +
{III}$"but got: {{transformed}}"
{II});
}}"""
            )
        )

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_wrap_helper())

    blocks.extend(container_blocks)

    writer = io.StringIO()
    writer.write(
        f"""\
internal class Wrapper<TEnhancement>
{I}: Our.Visitation.AbstractTransformer<Our.IClass>
{I}where TEnhancement : class
{{
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
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    namespace: csharp_common.NamespaceIdentifier,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for enhancing model classes.

    The ``namespace`` defines the base C# namespace of the generated code.
    """
    enhancing_blocks: List[Stripped] = [
        Stripped(
            f"""\
public abstract class Enhanced<TEnhancement> where TEnhancement : class
{{
{I}// ReSharper disable once InconsistentNaming
{I}protected readonly TEnhancement _enhancement;

{I}protected Enhanced(TEnhancement enhancement)
{I}{{
{II}_enhancement = enhancement;
{I}}}

{I}internal TEnhancement _getEnhancement()
{I}{{
{II}return _enhancement;
{I}}}
}}"""
        )
    ]

    errors: List[Error] = []

    for cls in symbol_table.concrete_classes:
        code, error = _generate_enhanced_class(cls=cls)
        if error is not None:
            errors.append(error)
            continue

        assert code is not None
        enhancing_blocks.append(code)
    wrapper, wrapper_errors = _generate_wrapper(symbol_table=symbol_table)
    if wrapper_errors is not None:
        errors.extend(wrapper_errors)

    if len(errors) > 0:
        return None, errors

    assert wrapper is not None
    enhancing_blocks.append(wrapper)

    enhancing_blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Unwrap enhancements from the wrapped instances.
/// </summary>
/// <typeparam name="TEnhancement">type of the enhancement</typeparam>
public class Unwrapper<TEnhancement> where TEnhancement : class
{{
{I}/// <summary>
{I}/// Unwrap the given model instance.
{I}/// </summary>
{I}/// <param name="that">model instance to be unwrapped</param>
{I}/// <returns>
{I}/// Enhancement, or <c>null</c> if <paramref name="that" />
{I}/// has not been wrapped yet.
{I}/// </returns>
{I}public TEnhancement? Unwrap(Our.IClass that)
{I}{{
{II}// ReSharper disable once SuspiciousTypeConversion.Global
{II}var enhanced = that as Enhanced<TEnhancement>;
{II}return enhanced?._getEnhancement();
{I}}}

{I}/// <summary>
{I}/// Unwrap the given model instance.
{I}/// </summary>
{I}/// <param name="that">model instance to be unwrapped</param>
{I}/// <returns>
{I}/// Enhancement wrapped around <paramref name="that" />
{I}/// </returns>
{I}/// <exception cref="System.ArgumentException">
{I}/// Thrown when <paramref name="that" /> has not been wrapped yet
{I}/// </exception>
{I}public TEnhancement MustUnwrap(Our.IClass that)
{I}{{
{II}return Unwrap(that) ?? throw new System.ArgumentException(
{III}$"Expected the instance to have been wrapped, but it was not: {{that}}"
{II});
{I}}}
}}  // public class Unwrapper"""
        )
    )

    enhancing_blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Wrap and unwrap the instances of model classes with enhancement.
/// </summary>
/// <typeparam name="TEnhancement">type of the enhancement</typeparam>
public class Enhancer<TEnhancement>
{I}: Unwrapper<TEnhancement>
{I}where TEnhancement : class
{{
{I}private readonly Wrapper<TEnhancement> _wrapper;

{I}/// <param name="enhancementFactory">
{I}/// <para>how to enhance the instances.</para>
{I}///
{I}/// <para>If it returns <c>null</c>, the instance will not be wrapped. However,
{I}/// the wrapping will continue recursively.</para>
{I}///</param>
{I}public Enhancer(
{II}System.Func<Our.IClass, TEnhancement?> enhancementFactory
{I})
{I}{{
{II}_wrapper = new Wrapper<TEnhancement>(enhancementFactory);
{I}}}

{I}/// <summary>
{I}/// Wrap the instance with an enhancement.
{I}/// </summary>
{I}/// <remarks>
{I}/// Double wraps are not allowed to prevent runtime leakage.
{I}///
{I}/// If you use references to the instance objects, you have to update them
{I}/// after the wrapping, as the wrapping is recursive.
{I}/// </remarks>
{I}/// <param name="that">model instance to be wrapped</param>
{I}/// <returns>
{I}/// <paramref name="that" /> instance wrapped recursively with enhancements
{I}/// </returns>
{I}/// <exception cref="System.ArgumentException">
{I}/// Thrown when <paramref name="that" /> has been already wrapped
{I}/// </exception>
{I}public Our.IClass Wrap(
{II}Our.IClass that
{I})
{I}{{
{II}var wrapped = _wrapper.Transform(that);
{II}return (
{III}wrapped
{II}) ?? throw new System.InvalidOperationException(
{III}"Expected the wrapped instance to be an instance of IClass, " +
{III}$"but got: {{wrapped}}"
{II});
{I}}}
}}  // public class Enhancer"""
        )
    )

    using_directives: List[Stripped] = []
    using_directives.extend(
        csharp_common.generate_using_our_directive_if_necessary(namespace)
    )

    if intermediate_uses.json_types(symbol_table):
        using_directives.append(Stripped("using Nodes = System.Text.Json.Nodes;"))

    using_directives.append(
        Stripped(
            """\
using System.Collections.Generic;  // can't alias"""
        )
    )

    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
    ]

    enhancing_writer = io.StringIO()
    enhancing_writer.write(
        f"""\
namespace {namespace}
{{
{I}/// <summary>
{I}/// Allow for enhancing of our model classes with custom wraps.
{I}/// </summary>
{I}public static class Enhancing
{I}{{
"""
    )

    for i, enhancing_block in enumerate(enhancing_blocks):
        if i > 0:
            enhancing_writer.write("\n\n")

        enhancing_writer.write(textwrap.indent(enhancing_block, II))

    enhancing_writer.write(f"\n{I}}}  // public static class Enhancing")
    enhancing_writer.write(f"\n}}  // namespace {namespace}")

    blocks.append(Stripped(enhancing_writer.getvalue()))

    blocks.append(csharp_common.WARNING)

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
