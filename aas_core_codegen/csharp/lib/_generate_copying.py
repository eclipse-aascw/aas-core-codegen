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
from aas_core_codegen.csharp import (
    common as csharp_common,
    naming as csharp_naming,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)


def _generate_shallow_copy_transform_method(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the method in the transformer to make a shallow copy of ``cls``."""
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

    cls_name = csharp_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        return_statement = Stripped(f"return new Aas.{cls_name}();")
    else:
        constructor_arg_exprs = []  # type: List[str]
        for arg in cls.constructor.arguments:
            prop_name = csharp_naming.property_name(arg.name)
            constructor_arg_exprs.append(f"that.{prop_name}")

        # NOTE (mristin, 2022-11-03):
        # This is poor man's heuristic for line breaking, but it works fairly well
        # in practice.
        args_joined = ", ".join(constructor_arg_exprs)
        return_statement = Stripped(f"return new Aas.{cls_name}({args_joined});")

        if len(return_statement) > 70:
            args_joined = ",\n".join(constructor_arg_exprs)
            return_statement = Stripped(
                f"""\
return new Aas.{cls_name}(
{I}{indent_but_first_line(args_joined, I)});"""
            )

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
public override Aas.IClass {transform_name}(
{I}Aas.{interface_name} that
)
{{
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
                f"Copying/ShallowCopier/transform_{cls.name}.cs"
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
/// <summary>Dispatch the making of shallow copies.</summary>
internal class ShallowCopier : Visitation.AbstractTransformer<Aas.IClass>
{
"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class ShallowCopier")

    return Stripped(writer.getvalue()), None


def _generate_deep_copy_transform_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the method in the transformer to make a deep copy of ``cls``."""
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

    cls_name = csharp_naming.class_name(cls.name)

    body_blocks = []  # type: List[Stripped]

    if len(cls.constructor.arguments) == 0:
        body_blocks.append(Stripped(f"return new Aas.{cls_name}();"))
    else:
        # NOTE (mristin):
        # We handle first the case of properties containing lists, and make copies of
        # the lists to separate variables. The variables are finally passed to
        # the constructor (see below, after this code of block).
        #
        # We could use LINQ to make deep copies of lists in expressions which are
        # directly passed to the constructor. This indeed makes sense if we wrote
        # the code manually, and would also be a more elegant solution. However,
        # LINQ comes with a certain overhead (for example, the memory for the new list
        # can not be pre-reserved ahead of time). That is why we make these copies in
        # separate variables and pass on the variables to the constructor.

        for arg in cls.constructor.arguments:
            prop_name = csharp_naming.property_name(arg.name)
            optional = isinstance(
                arg.type_annotation, intermediate.OptionalTypeAnnotation
            )

            type_anno = intermediate.beneath_optional(arg.type_annotation)

            if not isinstance(type_anno, intermediate.ListTypeAnnotation):
                continue

            # NOTE (mristin):
            # We need to prefix to avoid any possible naming conflicts.
            variable_name = csharp_naming.variable_name(Identifier(f"the_{arg.name}"))

            variable_type = csharp_common.generate_type(type_anno)

            # NOTE (mristin):
            # We can make much simpler copies for lists of primitives and enums, so
            # we optimize the generated code here.

            if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation) or (
                isinstance(type_anno.items, intermediate.OurTypeAnnotation)
                and isinstance(
                    type_anno.items.our_type,
                    (intermediate.Enumeration, intermediate.ConstrainedPrimitive),
                )
            ):
                primitive_type = intermediate.try_primitive_type(type_anno.items)

                # NOTE (mristin):
                # Byte arrays need deep copies -- all other lists can be simply copied.
                if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                    if not optional:
                        body_blocks.append(
                            Stripped(
                                f"""\
var {variable_name} = new {variable_type}(
{I}that.{prop_name}.Count);
foreach (var item in that.{prop_name})
{{
{I}{variable_name}.Add((byte[])item.Clone());
}}"""
                            )
                        )
                    else:
                        body_blocks.append(
                            Stripped(
                                f"""\
{variable_type}? {variable_name} = null;
if (that.{prop_name} != null)
{{
{I}{variable_name} = new {variable_type}(
{II}that.{prop_name}.Count);
{I}foreach (var item in that.{prop_name})
{I}{{
{II}{variable_name}.Add((byte[])item.Clone());
{I}}}
}}"""
                            )
                        )
                else:
                    # NOTE (mristin):
                    # We add the assertion here to force the developer to change
                    # the code in case that our assumption that the list items
                    # are copied by value does not hold anymore. For example, if another
                    # primitive type is introduced.

                    assert primitive_type in (
                        intermediate.PrimitiveType.BOOL,
                        intermediate.PrimitiveType.INT,
                        intermediate.PrimitiveType.FLOAT,
                        intermediate.PrimitiveType.STR,
                    ) or (
                        isinstance(type_anno.items, intermediate.OurTypeAnnotation)
                        and isinstance(
                            type_anno.items.our_type, intermediate.Enumeration
                        )
                    )

                    if not optional:
                        body_blocks.append(
                            Stripped(
                                f"""\
var {variable_name} = new {variable_type}(
{I}that.{prop_name});"""
                            )
                        )
                    else:
                        body_blocks.append(
                            Stripped(
                                f"""\
{variable_type}? {variable_name} = null;
if (that.{prop_name} != null)
{{
{I}{variable_name} = new {variable_type}(
{II}that.{prop_name});
}}"""
                            )
                        )

            elif isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ) and isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                if not optional:
                    body_blocks.append(
                        Stripped(
                            f"""\
var {variable_name} = new {variable_type}(
{I}that.{prop_name}.Count);
foreach (var item in that.{prop_name})
{{
{I}{variable_name}.Add(Deep(item));
}}"""
                        )
                    )
                else:
                    body_blocks.append(
                        Stripped(
                            f"""\
{variable_type}? {variable_name} = null;
if (that.{prop_name} != null)
{{
{I}{variable_name} = new {variable_type}(
{II}that.{prop_name}.Count);
{I}foreach (var item in that.{prop_name})
{I}{{
{II}{variable_name}.Add(Deep(item));
{I}}}
}}"""
                        )
                    )
            else:
                raise NotImplementedError(
                    "(mristin) We handle only lists of atomic values in the deep "
                    "copies at the moment. The meta-model does not contain "
                    "any other lists, so we wanted to keep the code as simple as "
                    "possible, and avoid unrolling. Please contact the developers "
                    "if you need this feature."
                )

        constructor_arg_exprs = []  # type: List[str]
        for arg in cls.constructor.arguments:
            prop_name = csharp_naming.property_name(arg.name)

            type_anno = intermediate.beneath_optional(arg.type_annotation)

            optional = isinstance(
                arg.type_annotation, intermediate.OptionalTypeAnnotation
            )

            if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
                constructor_arg_exprs.append(f"that.{prop_name}")

            elif isinstance(type_anno, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.our_type, intermediate.Enumeration):
                    constructor_arg_exprs.append(f"that.{prop_name}")

                elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                    constructor_arg_exprs.append(f"that.{prop_name}")

                elif isinstance(
                    type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    if optional:
                        constructor_arg_exprs.append(
                            f"""\
(that.{prop_name} != null)
{I}? Deep(that.{prop_name})
{I}: null"""
                        )
                    else:
                        constructor_arg_exprs.append(f"Deep(that.{prop_name})")
                else:
                    # noinspection PyTypeChecker
                    assert_never(type_anno.our_type)

            elif isinstance(type_anno, intermediate.ListTypeAnnotation):
                # NOTE (mristin):
                # See how this variable is computed above in the generated code.
                constructor_arg_exprs.append(
                    csharp_naming.variable_name(Identifier(f"the_{arg.name}"))
                )

            elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                # NOTE (mristin):
                # Tuples are fixed-length and heterogeneous, so, unlike lists, we can
                # construct the copy directly in-line without a pre-sized collection.
                item_exprs = []  # type: List[Stripped]
                for i, item_type_anno in enumerate(type_anno.items):
                    item_expr = f"that.{prop_name}.Item{i + 1}"

                    if isinstance(
                        item_type_anno, intermediate.OurTypeAnnotation
                    ) and isinstance(
                        item_type_anno.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        item_expr = f"Deep({item_expr})"

                    item_exprs.append(Stripped(item_expr))

                constructor_arg_exprs.append(
                    csharp_common.generate_tuple_literal(item_exprs)
                )
            else:
                # noinspection PyTypeChecker
                assert_never(type_anno)

        return_statement_writer = io.StringIO()

        return_statement_writer.write(f"return new Aas.{cls_name}(\n")

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

    interface_name = csharp_naming.interface_name(cls.name)
    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    return Stripped(
        f"""\
public override Aas.IClass {transform_name}(
{I}Aas.{interface_name} that
)
{{
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
                f"Copying/DeepCopier/transform_{cls.name}.cs"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The snippet for making deep copies is missing "
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
/// <summary>Dispatch the making of deep copies.</summary>
internal class DeepCopier : Visitation.AbstractTransformer<Aas.IClass>
{"""
    )

    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(block, I))

    writer.write("\n}  // internal class DeepCopier")

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
    Generate code for copying instances in memory.

    The ``namespace`` defines the AAS C# namespace.
    """
    errors = []  # type: List[Error]

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using System.Collections.Generic;  // can't alias"""
        )
    )

    # NOTE (mristin, 2022-11-03):
    # We wrap the shallow and deep copying in generic methods to allow for easier
    # enforcement of runtime type safety for the client. Otherwise, if we directly
    # provided the transformer, the client would always need to make the casts, which
    # is cumbersome.

    copy_blocks = [
        Stripped(
            f"""\
private static readonly ShallowCopier ShallowCopierInstance = (
{I}new ShallowCopier());"""
        ),
        Stripped(
            f"""\
private static readonly DeepCopier DeepCopierInstance = (
{I}new DeepCopier());"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Make a shallow copy of <paramref name="that" />.
/// </summary>
/// <remarks>
/// All the properties are copied by reference. This includes also the lists.
/// Hence, a list property is copied by reference, and not, as sometimes might be
/// expected, as a new list of underlying references.
/// </remarks>.
/// <param name="that">to be copied in a shallow manner</param>
/// <typeparam name="T">type to cast the result to</typeparam>
public static T Shallow<T>(T that) where T : Aas.IClass
{{
{I}return (T)ShallowCopierInstance.Transform(that);
}}"""
        ),
        Stripped(
            f"""\
/// <summary>
/// Make a recursively a deep copy of <paramref name="that" />.
/// </summary>
/// <param name="that">to be deeply copied in a recursive manner</param>
/// <typeparam name="T">type to cast the result to</typeparam>
public static T Deep<T>(T that) where T : Aas.IClass
{{
{I}return (T)DeepCopierInstance.Transform(that);
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
/// <summary>
/// Allow for making shallow and deep copies of AAS model instances.
/// </summary>
public static class Copying
{
"""
    )

    for i, copy_block in enumerate(copy_blocks):
        if i > 0:
            copying_writer.write("\n\n")

        copying_writer.write(textwrap.indent(copy_block, I))

    copying_writer.write("\n}  // public static class Copying")

    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(
            f"""\
namespace {namespace}
{{
{I}{indent_but_first_line(copying_writer.getvalue(), I)}
}}  // namespace {namespace}"""
        ),
        csharp_common.WARNING,
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        assert not block.startswith("\n")
        assert not block.endswith("\n")
        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
