"""Generate code for enhancing model classes."""

import io
import textwrap
from typing import Tuple, Optional, List

from icontract import ensure, require

from aas_core_codegen import intermediate, specific_implementations
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
    INDENT4 as IIII,
)


def _generate_delegate_method(method: intermediate.Method) -> Stripped:
    """Generate the delegated method to ``_instance``."""
    returns = (
        csharp_common.generate_type(method.returns, our_type_qualifier=Stripped("Aas"))
        if method.returns is not None
        else "void"
    )

    arg_types_names = [
        (
            csharp_common.generate_type(
                arg.type_annotation, our_type_qualifier=Stripped("Aas")
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
@require(lambda cls: not cls.is_implementation_specific)
def _generate_enhanced_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the structure for the enhanced concrete class."""
    enhanced_name = csharp_naming.class_name(Identifier(f"enhanced_{cls.name}"))
    interface_name = csharp_naming.interface_name(cls.name)

    blocks = [
        Stripped(f"private readonly Aas.{interface_name} _instance;"),
        Stripped(
            f"""\
public {enhanced_name}(
{I}Aas.{interface_name} instance,
{I}TEnhancement enhancement
) : base(enhancement)
{{
{I}_instance = instance;
}}"""
        ),
    ]  # type: List[Stripped]

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
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = csharp_naming.property_name(prop.name)
            items_type = csharp_common.generate_type(
                prop.type_annotation.value.items, our_type_qualifier=Stripped("Aas")
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
        blocks.append(_generate_delegate_method(method))

    visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks.extend(
        [
            Stripped(
                f"""\
public IEnumerable<Aas.IClass> DescendOnce()
{{
{I}return _instance.DescendOnce();
}}"""
            ),
            Stripped(
                f"""\
public IEnumerable<Aas.IClass> Descend()
{{
{I}return _instance.Descend();
}}"""
            ),
            Stripped(
                f"""\
public void Accept(Aas.Visitation.IVisitor visitor)
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
{I}: Enhanced<TEnhancement>, Aas.{interface_name}
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


def _generate_union_transform_helper() -> Stripped:
    """
    Generate a single ``Transform`` overload shared by every named union.

    A named union is not itself an ``Aas.IClass``, so it can not be dispatched
    by the inherited, ``IClass``-typed ``Transform`` overload, and its
    underlying instance has to be unwrapped, enhanced and wrapped back up.
    We add this overload, single-purpose, next to the per-class ``Transform``
    overrides, so that call sites can keep passing ``Transform`` around as
    a plain method group or calling it directly, regardless of whether the
    value at hand is a class instance or a named union.

    ``T`` is bounded by ``Aas.IUnion<T>`` (see ``generate()`` in
    ``_generate_types.py``) instead of by the union's own type, so we need
    only this one overload for *all* named unions, not one per union.
    Unlike the per-class ``Transform(Aas.IClass that)`` (non-generic, plain
    ``IClass``-typed, inherited from ``AbstractTransformer<Aas.IClass>``),
    this overload returns ``T`` itself, since re-wrapping with
    ``WithUnderlying`` already recovers the caller's own concrete union type
    exactly -- so call sites need no downcast.

    .. note::

        The parameter is typed as ``Aas.IUnion<T>``, not bare ``T`` --
        confirmed with a real, minimal ``dotnet build`` reproduction that a
        bare-``T`` signature here breaks the recursive call inside this
        very method's own body (``Transform(that.Underlying)``, where
        ``that.Underlying`` is plain ``Aas.IClass``): C# resolves that call
        against *this* generic method itself (inferring ``T = Aas.IClass``)
        rather than falling back to the inherited, non-generic
        ``Transform(Aas.IClass that)``, and only then fails the ``where T :
        Aas.IUnion<T>`` constraint (CS0311) -- a tie in "exactness" between
        a generic method (post-substitution) and a non-generic one is
        broken in favor of the generic one, so the non-generic overload is
        effectively unreachable by unqualified calls from inside a
        bare-``T`` version of this method. Typing the parameter as ``Aas.
        IUnion<T>`` removes ``Aas.IClass`` from the generic overload's
        applicable argument types entirely (``Aas.IClass`` does not
        implement ``Aas.IUnion<T>`` for any ``T``), so
        ``Transform(that.Underlying)`` has only the non-generic overload to
        choose from -- no ambiguity. (Copying's ``Deep<T>`` needed the same
        ``Aas.IUnion<T>`` parameter shape, but for the different reason of
        avoiding a duplicate-signature clash with its sibling
        ``Deep<T>(T that) where T : Aas.IClass``, since both of *its*
        overloads are generic -- see
        :py:func:`_generate_union_deep_copy_helper` in
        ``_generate_copying.py``.)

    Should a named union ever be allowed to flatten primitive or enumeration
    alternatives, only the body of this method has to change (to dispatch on
    the underlying value's kind) -- every call site stays the same.
    """
    return Stripped(
        f"""\
private T Transform<T>(Aas.IUnion<T> that) where T : Aas.IUnion<T>
{{
{I}return that.WithUnderlying(
{II}Transform(that.Underlying));
}}"""
    )


@require(lambda cls: not cls.is_implementation_specific)
def _generate_transform(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method to wrap the instance with an enhancement."""
    blocks = [
        Stripped(
            f"""\
if (that is Enhanced<TEnhancement>)
{{
{I}throw new System.ArgumentException(
{II}$"The instance has been already enhanced: {{that}}"
{I});
}}"""
        )
    ]  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)
        prop_name = csharp_naming.property_name(prop.name)

        wrap_stmt: Stripped

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            # We can not enhance primitive types; nothing to do here.
            continue

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                # We can not enhance enumerations; nothing to do here.
                continue

            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                # We can not enhance primitive types; nothing to do here.
                continue

            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                value_interface_name = csharp_naming.interface_name(
                    type_anno.our_type.name
                )
                transformed_name = csharp_naming.variable_name(
                    Identifier(f"transformed_{prop.name}")
                )
                casted_name = csharp_naming.variable_name(
                    Identifier(f"casted_{prop.name}")
                )
                wrap_stmt = Stripped(
                    f"""\
var {transformed_name} = Transform(
{I}that.{prop_name}
);
var {casted_name} = (
{I}{transformed_name} as Aas.{value_interface_name}
) ?? throw new System.InvalidOperationException(
{I}"Expected the transformed value to be a {value_interface_name}, " +
{I}$"but got: {{{transformed_name}}}"
);
that.{prop_name} = {casted_name};"""
                )

            elif isinstance(type_anno.our_type, intermediate.NamedUnion):
                # A named union has its own ``Transform`` overload (see
                # :py:func:`_generate_union_transform_helper`), which
                # already returns the union's own type, so no downcast is
                # needed here (unlike the class branch above).
                wrap_stmt = Stripped(f"that.{prop_name} = Transform(that.{prop_name});")

            else:
                assert_never(type_anno.our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
                # We can not enhance primitive types; nothing to do here.
                continue

            elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                    # We can not enhance enumerations; nothing to do here.
                    continue

                elif isinstance(
                    type_anno.items.our_type, intermediate.ConstrainedPrimitive
                ):
                    # We can not enhance primitive types; nothing to do here.
                    continue

                elif isinstance(
                    type_anno.items.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    item_interface_name = csharp_naming.interface_name(
                        type_anno.items.our_type.name
                    )

                    wrap_stmt = Stripped(
                        f"""\
that.{prop_name} = (
{I}that.{prop_name}
{I}.Select(
{II}(item) => {{
{III}var transformed = Transform(item);
{III}return (
{IIII}transformed as Aas.{item_interface_name}
{III}) ?? throw new System.InvalidOperationException(
{IIII}"Expected the transformed item to be a {item_interface_name}, " +
{IIII}$"but got: {{transformed}}"
{III});
{II}}}
{I})
).ToList();"""
                    )

                elif isinstance(type_anno.items.our_type, intermediate.NamedUnion):
                    # A named union has its own ``Transform`` overload (see
                    # :py:func:`_generate_union_transform_helper`),
                    # which already returns the union's own type, so it can
                    # be passed on as a bare method group with no wrapping
                    # lambda (unlike the class branch above, which needs one
                    # to downcast).
                    wrap_stmt = Stripped(
                        f"""\
that.{prop_name} = (
{I}that.{prop_name}
{I}.Select(Transform)
).ToList();"""
                    )

                else:
                    assert_never(type_anno.items.our_type)
            else:
                raise NotImplementedError(
                    f"(mristin) We handle only lists of classes and named unions "
                    f"in the enhancing at the moment. The meta-model does not "
                    f"contain any other lists, so we wanted to keep the code as "
                    f"simple as possible, and avoid unrolling. However, you desire "
                    f"a list of type {type_anno} to be enhanced. "
                    f"Please contact the developers if you need this feature."
                )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            pre_stmts = []  # type: List[Stripped]
            item_exprs = []  # type: List[Stripped]
            any_transformable_item = False

            for i, item_type_anno in enumerate(type_anno.items):
                item_access = Stripped(f"that.{prop_name}.Item{i + 1}")

                if isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    any_transformable_item = True

                    item_interface_name = csharp_naming.interface_name(
                        item_type_anno.our_type.name
                    )
                    transformed_name = csharp_naming.variable_name(
                        Identifier(f"transformed_{prop.name}_{i}")
                    )
                    casted_name = csharp_naming.variable_name(
                        Identifier(f"casted_{prop.name}_{i}")
                    )

                    pre_stmts.append(
                        Stripped(
                            f"""\
var {transformed_name} = Transform(
{I}{item_access}
);
var {casted_name} = (
{I}{transformed_name} as Aas.{item_interface_name}
) ?? throw new System.InvalidOperationException(
{I}"Expected the transformed value to be a {item_interface_name}, " +
{I}$"but got: {{{transformed_name}}}"
);"""
                        )
                    )

                    item_exprs.append(Stripped(casted_name))

                elif isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(item_type_anno.our_type, intermediate.NamedUnion):
                    # A named union has its own ``Transform`` overload (see
                    # :py:func:`_generate_union_transform_helper`),
                    # which already returns the union's own type, so no
                    # downcast (and hence no pre-statement) is needed here,
                    # unlike the class branch above.
                    any_transformable_item = True

                    item_exprs.append(Stripped(f"Transform({item_access})"))

                else:
                    item_exprs.append(item_access)

            if not any_transformable_item:
                # We can not enhance any of the tuple items; nothing to do here.
                continue

            tuple_literal = csharp_common.generate_tuple_literal(item_exprs)

            if len(pre_stmts) == 0:
                wrap_stmt = Stripped(f"that.{prop_name} = {tuple_literal};")
            else:
                joined_pre_stmts = "\n\n".join(pre_stmts)
                wrap_stmt = Stripped(
                    f"""\
{joined_pre_stmts}
that.{prop_name} = {tuple_literal};"""
                )
        else:
            assert_never(type_anno)

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            wrap_stmt = Stripped(
                f"""\
if (that.{prop_name} != null)
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
public override Aas.IClass {transform_name}(
{I}Aas.{interface_name} that
)
{{
{I}{indent_but_first_line(blocks_joined, I)}
}}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_wrapper(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    """Generate the transformer that wraps an instance with the enhancement."""
    errors = []  # type: List[Error]
    blocks = [
        Stripped(
            "private readonly System.Func<Aas.IClass, TEnhancement?> "
            "_enhancementFactory;"
        ),
        Stripped(
            f"""\
internal Wrapper(
{I}System.Func<Aas.IClass, TEnhancement?> enhancementFactory
)
{{
{I}_enhancementFactory = enhancementFactory;
}}"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Enhancing/Wrap/{cls.name}.cs"
            )

            code = spec_impls.get(implementation_key, None)
            if code is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The implementation is missing "
                        f"for the implementation-specific class: {implementation_key}",
                    )
                )
                continue

            blocks.append(code)
            continue

        blocks.append(_generate_transform(cls=cls))

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_union_transform_helper())

    writer = io.StringIO()
    writer.write(
        f"""\
internal class Wrapper<TEnhancement>
{I}: Aas.Visitation.AbstractTransformer<Aas.IClass>
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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code for enhancing model classes.

    The ``namespace`` defines the AAS C# namespace.
    """
    enhancing_blocks = [
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
    ]  # type: List[Stripped]

    errors = []  # type: List[Error]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Enhancing/Enhanced/{cls.name}.cs"
            )

            code = spec_impls.get(implementation_key, None)
            if code is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The implementation is missing "
                        f"for the implementation-specific class: {implementation_key}",
                    )
                )
                continue

            assert code is not None
            enhancing_blocks.append(code)
        else:
            code, error = _generate_enhanced_class(cls=cls)
            if error is not None:
                errors.append(error)
                continue

            assert code is not None
            enhancing_blocks.append(code)

    wrapper, wrapper_errors = _generate_wrapper(
        symbol_table=symbol_table, spec_impls=spec_impls
    )
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
{I}public TEnhancement? Unwrap(Aas.IClass that)
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
{I}public TEnhancement MustUnwrap(Aas.IClass that)
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
{II}System.Func<Aas.IClass, TEnhancement?> enhancementFactory
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
{I}public Aas.IClass Wrap(
{II}Aas.IClass that
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

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using System.Collections.Generic;  // can't alias
using System.Linq;  // can't alias"""
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
