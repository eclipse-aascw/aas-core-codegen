"""Generate code for enhancing model classes."""

import io
import textwrap
from typing import Tuple, Optional, List

from icontract import ensure, require

from aas_core_codegen import intermediate, specific_implementations
from aas_core_codegen.common import (
    Error,
    Identifier,
    assert_never,
    Stripped,
    indent_but_first_line,
)
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

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.enhancing;"),
        enhanced,
        java_common.WARNING,
    ]  # type: List[Stripped]

    code = "\n\n".join(blocks)

    return java_common.JavaFile(
        "Enhanced.java",
        f"{code}\n",
    )


def _generate_unwrapper_class(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    imports = [
        Stripped("import java.util.Optional;"),
        Stripped(f"import {package}.types.model.*;"),
    ]  # type: List[Stripped]

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

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.enhancing;"),
        Stripped("\n".join(imports)),
        unwrapper,
        java_common.WARNING,
    ]  # type: List[Stripped]

    code = "\n\n".join(blocks)

    return java_common.JavaFile(
        "Unwrapper.java",
        f"{code}\n",
    )


def _generate_enhancer_class(
    package: java_common.PackageIdentifier,
) -> java_common.JavaFile:
    imports = [
        Stripped("import java.util.function.Function;"),
        Stripped("import java.util.Optional;"),
        Stripped(f"import {package}.enhancing.Unwrapper;"),
        Stripped(f"import {package}.types.model.*;"),
    ]  # type: List[Stripped]

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

    blocks = [
        java_common.WARNING,
        Stripped(f"package {package}.enhancing;"),
        Stripped("\n".join(imports)),
        enhancer,
        java_common.WARNING,
    ]  # type: List[Stripped]

    code = "\n\n".join(blocks)

    return java_common.JavaFile(
        "Enhancer.java",
        f"{code}\n",
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@require(lambda cls: not cls.is_implementation_specific)
def _generate_enhanced_class(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
# fmt: on
    """Generate the structure for the enhanced concrete class."""
    enhanced_name = java_naming.class_name(Identifier(f"enhanced_{cls.name}"))
    interface_name = java_naming.interface_name(cls.name)

    blocks = [
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
    ]  # type: List[Stripped]

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
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    files = []  # type: List[java_common.JavaFile]

    errors = []  # type: List[Error]

    for cls in symbol_table.concrete_classes:
        cls_name = java_naming.class_name(cls.name)

        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Enhancing/Enhanced/{cls.name}.java"
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

            files.append(
                java_common.JavaFile(
                    f"{cls_name}.java",
                    f"{code}\n",
                ),
            )
        else:
            code, error = _generate_enhanced_class(cls=cls)
            if error is not None:
                errors.append(error)
                continue

            assert code is not None

            imports = [
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
            ]  # type: List[Stripped]

            blocks = [
                java_common.WARNING,
                Stripped(f"package {package}.enhancing;"),
                Stripped("\n".join(imports)),
                code,
                java_common.WARNING,
            ]  # type: List[Stripped]

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


@require(lambda cls: not cls.is_implementation_specific)
def _generate_transform(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the transform method to wrap the instance with an enhancement."""
    blocks = [
        Stripped(
            f"""\
if (that instanceof Enhanced)
{{
{I}throw new IllegalArgumentException(
{II}"The instance has been already enhanced: " + that
{I});
}}"""
        )
    ]  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)
        prop_name = java_naming.property_name(prop.name)

        optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

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
                getter_name = java_naming.getter_name(prop.name)
                setter_name = java_naming.setter_name(prop.name)
                value_interface_name = java_naming.interface_name(
                    type_anno.our_type.name
                )
                transformed_name = java_naming.variable_name(
                    Identifier(f"transformed_{prop.name}")
                )
                casted_name = java_naming.variable_name(
                    Identifier(f"casted_{prop.name}")
                )

                stmt = Stripped(
                    f"""\
IClass {transformed_name} = transform({prop_name});
if (!({transformed_name} instanceof {value_interface_name})) {{
{I}throw new UnsupportedOperationException(
{II}"Expected the transformed value to be a {value_interface_name} " +
{II}", but got: " + {transformed_name}
{I});
}}
{value_interface_name} {casted_name} = ({value_interface_name}) {transformed_name};
that.{setter_name}({casted_name});"""
                )

                writer = io.StringIO()

                if optional:
                    writer.write(
                        f"""\
if (that.{getter_name}().isPresent()) {{
{I}{value_interface_name} {prop_name} = that.{getter_name}().get();
{I}{indent_but_first_line(stmt, I)}
}}"""
                    )
                else:
                    writer.write(
                        f"""\
{value_interface_name} {prop_name} = that.{getter_name}();
{stmt}"""
                    )

                wrap_stmt = Stripped(writer.getvalue())
            else:
                assert_never(type_anno.our_type)
        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            # fmt: off
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "We handle only lists of atomic values (primitives, constrained "
                "primitives, enumeration literals) or lists of classes in the "
                "enhancing at the moment. Lists of lists or lists of optionals "
                "are not supported. Please contact the developers if you need "
                "this feature."
            )
            # fmt: on

            if not (
                isinstance(type_anno.items, intermediate.OurTypeAnnotation)
                and isinstance(
                    type_anno.items.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                )
            ):
                # We can not enhance lists of primitives, constrained
                # primitives or enumeration literals; nothing to do here.
                continue

            item_interface_name = java_naming.interface_name(
                type_anno.items.our_type.name
            )
            transformed_name = java_naming.variable_name(
                Identifier(f"transformed_{prop.name}")
            )

            getter_name = java_naming.getter_name(prop.name)

            setter_name = java_naming.setter_name(prop.name)

            stmt = Stripped(
                f"""\
List<{item_interface_name}> {transformed_name} = {prop_name}.stream()
{I}.map(item -> {{
{II}IClass transformed = transform(item);
{II}if (!(transformed instanceof {item_interface_name})) {{
{III}throw new UnsupportedOperationException(
{IIII}"Expected the transformed value to be a {item_interface_name} " +
{IIII}", but got: " + transformed
{III});
{II}}}
{II}return ({item_interface_name}) transformed;
{I}}}).collect(Collectors.toList());
that.{setter_name}({transformed_name});"""
            )

            writer = io.StringIO()

            if optional:
                writer.write(
                    f"""\
if (that.{getter_name}().isPresent()) {{
{I}List<{item_interface_name}> {prop_name} = that.{getter_name}().get();
{I}{indent_but_first_line(stmt, I)}
}}"""
                )
            else:
                writer.write(
                    f"""\
List<{item_interface_name}> {prop_name} = that.{getter_name}();
{stmt}"""
                )

            wrap_stmt = Stripped(writer.getvalue())
        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            if not any(
                isinstance(item, intermediate.OurTypeAnnotation)
                and isinstance(
                    item.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                )
                for item in type_anno.items
            ):
                # We can not enhance tuples none of whose items are classes;
                # nothing to do here.
                continue

            tuple_type = java_common.generate_type(type_anno)

            getter_name = java_naming.getter_name(prop.name)
            setter_name = java_naming.setter_name(prop.name)

            item_stmts = []  # type: List[Stripped]
            item_exprs = []  # type: List[Stripped]

            for i, item_type_anno in enumerate(type_anno.items):
                item_access = Stripped(f"{prop_name}.item{i + 1}()")

                if isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    item_interface_name = java_naming.interface_name(
                        item_type_anno.our_type.name
                    )
                    transformed_name = java_naming.variable_name(
                        Identifier(f"transformed_{prop.name}_{i}")
                    )
                    casted_name = java_naming.variable_name(
                        Identifier(f"casted_{prop.name}_{i}")
                    )

                    item_stmts.append(
                        Stripped(
                            f"""\
IClass {transformed_name} = transform({item_access});
if (!({transformed_name} instanceof {item_interface_name})) {{
{I}throw new UnsupportedOperationException(
{II}"Expected the transformed value to be a {item_interface_name} " +
{II}", but got: " + {transformed_name}
{I});
}}
{item_interface_name} {casted_name} = ({item_interface_name}) {transformed_name};"""
                        )
                    )

                    item_exprs.append(Stripped(casted_name))
                else:
                    item_exprs.append(item_access)

            tuple_literal = java_common.generate_tuple_literal(item_exprs=item_exprs)

            stmt_parts = item_stmts + [
                Stripped(
                    f"""\
that.{setter_name}(
{I}{indent_but_first_line(tuple_literal, I)});"""
                )
            ]

            stmt = Stripped("\n".join(stmt_parts))

            writer = io.StringIO()

            if optional:
                writer.write(
                    f"""\
if (that.{getter_name}().isPresent()) {{
{I}{tuple_type} {prop_name} = that.{getter_name}().get();
{I}{indent_but_first_line(stmt, I)}
}}"""
                )
            else:
                writer.write(
                    f"""\
{tuple_type} {prop_name} = that.{getter_name}();
{stmt}"""
                )

            wrap_stmt = Stripped(writer.getvalue())
        else:
            assert_never(type_anno.our_type)

        blocks.append(wrap_stmt)

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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[java_common.JavaFile], Optional[List[Error]]]:
    """Generate the transformer that wraps an instance with the enhancement."""
    errors = []  # type: List[Error]
    imports = [
        Stripped("import java.util.List;"),
        Stripped("import java.util.Optional;"),
        Stripped("import java.util.function.Function;"),
        Stripped("import java.util.stream.Collectors;"),
        Stripped("import java.util.stream.Stream;"),
        Stripped(f"import {package}.common.*;"),
        Stripped(f"import {package}.types.enums.*;"),
        Stripped(f"import {package}.types.model.*;"),
        Stripped(f"import {package}.visitation.AbstractTransformer;"),
    ]  # type: List[Stripped]
    body = [
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
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Enhancing/Wrap/{cls.name}.java"
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

            body.append(code)
            continue

        body.append(_generate_transform(cls=cls))

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

    blocks = [
        Stripped(java_common.WARNING),
        Stripped(Stripped(f"package {package}.enhancing;")),
        Stripped("\n".join(imports)),
        Stripped(writer.getvalue()),
        Stripped(java_common.WARNING),
    ]  # type: List[Stripped]

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
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[List[java_common.JavaFile]], Optional[List[Error]]]:
    """
    Generate code for enhancing model classes.
    """

    errors = []  # type: List[Error]

    java_files = [
        _generate_enhanced_abstract_class(package),
        _generate_unwrapper_class(package),
        _generate_enhancer_class(package),
    ]  # type: List[java_common.JavaFile]

    enhanced_files, enhanced_errors = _generate_enhanced(
        symbol_table, package, spec_impls
    )

    if enhanced_errors is not None:
        errors.extend(enhanced_errors)
    else:
        assert enhanced_files is not None

        java_files.extend(enhanced_files)

    wrapper_file, wrapper_errors = _generate_wrapper(symbol_table, package, spec_impls)

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
