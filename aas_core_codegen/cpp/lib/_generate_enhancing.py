"""Generate code for enhancing model classes."""

import io
from typing import Tuple, Optional, List, Sequence

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.cpp import (
    common as cpp_common,
    naming as cpp_naming,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)


def _generate_wrap_forward_declarations(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate the forward declarations of the overloaded ``Wrap`` functions."""
    result = []  # type: List[Stripped]
    for cls in symbol_table.classes:
        interface_name = cpp_naming.interface_name(cls.name)

        function_name = cpp_naming.function_name(Identifier("wrap"))

        result.append(
            Stripped(
                f"""\
template <typename E>
std::shared_ptr<
{I}types::{interface_name}
> {function_name}(
{I}const std::shared_ptr<
{II}types::{interface_name}
{I}>& that,
{I}const std::function<
{II}std::shared_ptr<E>(
{III}const std::shared_ptr<types::IClass>&
{II})
{I}>& factory
);"""
            )
        )

    return result


def _generate_enhanced_interface_definition() -> Stripped:
    """Generate the definition of the generic ``Enhanced`` interface."""
    enhanced_interface = cpp_naming.interface_name(Identifier("Enhanced"))

    members = []  # type: List[Stripped]

    enhancement_getter = cpp_naming.getter_name(Identifier("enhancement"))
    members.append(
        Stripped(
            f"""\
virtual const std::shared_ptr<E>& {enhancement_getter}() const = 0;"""
        )
    )

    enhancement_mutable_getter = cpp_naming.mutable_getter_name(
        Identifier("enhancement")
    )
    members.append(
        Stripped(
            f"""\
virtual std::shared_ptr<E>& {enhancement_mutable_getter}() = 0;"""
        )
    )

    enhancement_setter = cpp_naming.setter_name(Identifier("enhancement"))
    members.append(
        Stripped(
            f"""\
virtual void {enhancement_setter}(
{I}std::shared_ptr<E> value
) = 0;"""
        )
    )

    members.append(
        Stripped(
            f"""\
virtual ~{enhanced_interface}() = default;"""
        )
    )

    members_joined = "\n\n".join(members)

    return Stripped(
        f"""\
template<typename E>
class {enhanced_interface} {{
 public:
{I}{indent_but_first_line(members_joined, I)}
}};"""
    )


def _generate_method_delegation(method: intermediate.Method) -> Stripped:
    """Generate the delegated method to ``instance_``."""
    returns = (
        cpp_common.generate_type(method.returns, types_namespace=Identifier("types"))
        if method.returns is not None
        else None
    )

    return_type = "void" if returns is None else returns
    return_prefix = "" if returns is None else "return "

    arg_types_names = [
        (
            cpp_common.generate_type_with_const_ref_if_applicable(
                arg.type_annotation, types_namespace=Identifier("types")
            ),
            cpp_naming.argument_name(arg.name),
        )
        for arg in method.arguments
    ]

    method_name = cpp_naming.method_name(method.name)

    const_suffix = " const" if method.non_mutating else ""

    if len(method.arguments) == 0:
        return Stripped(
            f"""\
{return_type} {method_name}(){const_suffix} override {{
{I}{return_prefix}instance_->{method_name}();
}}"""
        )

    arguments_definition = ",\n".join(
        f"{arg_type} {arg_name}" for arg_type, arg_name in arg_types_names
    )

    arguments_delegation = ",\n".join(f"{arg_name}" for _, arg_name in arg_types_names)

    return Stripped(
        f"""\
{return_type} {method_name}(
{I}{indent_but_first_line(arguments_definition, I)}
){const_suffix} override {{
{I}{return_prefix}instance_->{method_name}(
{II}{indent_but_first_line(arguments_delegation, II)}
{I});
}}"""
    )


def _generate_enhanced_class(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """Generate the implementation of an enhanced class which wraps an instance."""
    public_members = []  # type: List[Stripped]

    model_type_enum = cpp_naming.enum_name(Identifier("Model_type"))
    model_type_getter = cpp_naming.getter_name(Identifier("model_type"))

    model_type_literal = cpp_naming.enum_literal_name(Identifier(cls.name))

    public_members.append(
        Stripped(
            f"""\
types::{model_type_enum} {model_type_getter}() const override {{
{I}return types::{model_type_enum}::{model_type_literal};
}}"""
        )
    )

    for prop in cls.properties:
        getter_name = cpp_naming.getter_name(prop.name)

        getter_type = cpp_common.generate_type_with_const_ref_if_applicable(
            type_annotation=prop.type_annotation, types_namespace=Identifier("types")
        )

        public_members.append(
            Stripped(
                f"""\
{getter_type} {getter_name}() const override {{
{I}return instance_->{getter_name}();
}}"""
            )
        )

        mutable_getter_name = cpp_naming.mutable_getter_name(prop.name)
        mutable_getter_type = cpp_common.generate_type_with_ref(
            type_annotation=prop.type_annotation, types_namespace=Identifier("types")
        )
        public_members.append(
            Stripped(
                f"""\
{mutable_getter_type} {mutable_getter_name}() override {{
{I}return instance_->{mutable_getter_name}();
}}"""
            )
        )

        setter_name = cpp_naming.setter_name(prop.name)

        # NOTE (mristin):
        # For a discussion on ``std::shared_ptr`` and referencing,
        # see: https://herbsutter.com/2013/06/05/gotw-91-solution-smart-pointer-parameters/

        # NOTE (mristin):
        # We provide setters which only set-by-value logic since this seems to be
        # the best approach for general cases,
        # see: https://stackoverflow.com/questions/10692345/is-it-worth-adding-a-move-enabled-setter.
        #
        # Whenever you know that you do not need the value after calling the setter,
        # make sure to call it with ``std::move(.)``.

        value_type = cpp_common.generate_type(
            type_annotation=prop.type_annotation, types_namespace=Identifier("types")
        )
        public_members.append(
            Stripped(
                f"""\
void {setter_name}(
{I}{indent_but_first_line(value_type, I)} value
) override {{
{I}instance_->{setter_name}(value);
}}"""
            )
        )

    for method in cls.methods:
        public_members.append(_generate_method_delegation(method=method))

    enhancement_getter = cpp_naming.getter_name(Identifier("enhancement"))
    public_members.append(
        Stripped(
            f"""\
const std::shared_ptr<E>& {enhancement_getter}() const {{
{I}return enhancement_;
}}"""
        )
    )

    enhancement_mutable_getter = cpp_naming.mutable_getter_name(
        Identifier("enhancement")
    )
    public_members.append(
        Stripped(
            f"""\
std::shared_ptr<E>& {enhancement_mutable_getter}() {{
{I}return enhancement_;
}}"""
        )
    )

    # NOTE (mristin):
    # See: https://stackoverflow.com/questions/41871115/why-would-i-stdmove-an-stdshared-ptr
    # for why we ``std::move`` here.
    enhancement_setter = cpp_naming.setter_name(Identifier("enhancement"))
    public_members.append(
        Stripped(
            f"""\
void {enhancement_setter}(
{I}std::shared_ptr<E> value
) {{
{I}enhancement_ = std::move(value);
}}"""
        )
    )

    enhanced_cls_name = cpp_naming.class_name(Identifier(f"enhanced_{cls.name}"))
    interface_name = cpp_naming.interface_name(cls.name)

    public_members.append(
        Stripped(
            f"""\
{enhanced_cls_name}(
{I}std::shared_ptr<types::{interface_name}> instance,
{I}std::shared_ptr<E> enhancement
) :
{I}instance_(instance),
{I}enhancement_(enhancement) {{
{I}// Intentionally empty.
}}"""
        )
    )

    public_members.append(
        Stripped(
            f"""\
virtual ~{enhanced_cls_name}() = default;"""
        )
    )

    public_members_joined = "\n\n".join(public_members)
    enhanced_interface = cpp_naming.interface_name(Identifier("Enhanced"))

    return Stripped(
        f"""\
template<class E>
class {enhanced_cls_name}
{II}: virtual public types::{interface_name},
{II}virtual public {enhanced_interface}<E> {{
 public:
{I}{indent_but_first_line(public_members_joined, I)}

 private:
{I}std::shared_ptr<types::{interface_name}> instance_;
{I}std::shared_ptr<E> enhancement_;
}};"""
    )


# NOTE (mristin):
# We write two separate functions, ``_generate_wrap_snippet_for_required_property`` and
# ``_generate_wrap_snippet_for_optional_property``, as the complexity grew over the top.
# This resulted in a much more readable code than if we tried to de-DRY the logic
# in a single function.


@require(lambda prop: not isinstance(prop, intermediate.OptionalTypeAnnotation))
def _generate_wrap_snippet_for_required_property(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the snippet to recursively wrap the required property.

    We return an empty string if there is no snippet for the property.
    """
    type_anno = prop.type_annotation

    # NOTE (mristin):
    # Duplicate the pre-condition for mypy.
    assert not isinstance(type_anno, intermediate.OptionalTypeAnnotation)

    setter_name = cpp_naming.setter_name(prop.name)

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        # Nothing to recurse into.
        return Stripped("")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            # Nothing to recurse into.
            return Stripped("")

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            # Nothing to recurse into.
            return Stripped("")

        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin):
            # The non-mutating getter means here that we will not change the reference,
            # but we want to recurse into the object.
            getter_name = cpp_naming.getter_name(prop.name)

            return Stripped(
                f"""\
that->{setter_name}(
{I}Wrap<E>(
{II}that->{getter_name}(),
{II}factory
{I})
);"""
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)

    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
            # Nothing to recurse into.
            return Stripped("")

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                # Nothing to recurse into.
                return Stripped("")

            elif isinstance(
                type_anno.items.our_type, intermediate.ConstrainedPrimitive
            ):
                # Nothing to recurse into.
                return Stripped("")

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                getter_name = cpp_naming.getter_name(prop.name)

                const_ref_prop_type = (
                    cpp_common.generate_type_with_const_ref_if_applicable(
                        type_annotation=type_anno, types_namespace=Identifier("types")
                    )
                )

                prop_type = cpp_common.generate_type(
                    type_annotation=type_anno,
                    types_namespace=cpp_common.TYPES_NAMESPACE,
                )

                item_type = cpp_common.generate_type_with_const_ref_if_applicable(
                    type_annotation=type_anno.items,
                    types_namespace=cpp_common.TYPES_NAMESPACE,
                )

                return Stripped(
                    f"""\
{{
{I}{indent_but_first_line(const_ref_prop_type, I)} value(
{II}that->{getter_name}()
{I});
{I}const std::size_t size = value.size();

{I}{indent_but_first_line(prop_type, I)} wrapped;
{I}wrapped.reserve(size);

{I}for (
{II}{indent_but_first_line(item_type, II)} item
{II}: value
{I}) {{
{II}wrapped.emplace_back(
{III}Wrap<E>(
{IIII}item,
{IIII}factory
{III})
{II});
{I}}}

{I}that->{setter_name}(
{II}std::move(wrapped)
{I});
}}"""
                )

            else:
                assert_never(type_anno.items.our_type)

        elif isinstance(type_anno.items, intermediate.OptionalTypeAnnotation):
            raise NotImplementedError(
                f"NOTE (mristin, 2026-05-09): We do not currently support "
                f"the generation of enhancing code for lists of optionals, "
                f"but you specified {type_anno}. Please contact the developers if "
                f"you need this feature."
            )

        elif isinstance(type_anno.items, intermediate.ListTypeAnnotation):
            raise NotImplementedError(
                f"NOTE (mristin, 2026-05-09): We do not currently support "
                f"the generation of enhancing code for lists of lists, "
                f"but you specified {type_anno}. Please contact the developers if "
                f"you need this feature."
            )

        elif isinstance(type_anno.items, intermediate.TupleTypeAnnotation):
            raise NotImplementedError(
                f"NOTE (mristin): We do not currently support "
                f"the generation of enhancing code for lists of tuples, "
                f"but you specified {type_anno}. Please contact the developers if "
                f"you need this feature."
            )

        else:
            assert_never(type_anno.items)

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        class_indices = []  # type: List[int]
        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            if isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(
                item_type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                class_indices.append(i)

        if len(class_indices) == 0:
            # Nothing to recurse into.
            return Stripped("")

        getter_name = cpp_naming.getter_name(prop.name)

        const_ref_prop_type = cpp_common.generate_type_with_const_ref_if_applicable(
            type_annotation=type_anno, types_namespace=Identifier("types")
        )

        prop_type = cpp_common.generate_type(
            type_annotation=type_anno,
            types_namespace=cpp_common.TYPES_NAMESPACE,
        )

        wrap_stmts = [
            Stripped(
                f"""\
std::get<{i}>(wrapped) = Wrap<E>(
{I}std::get<{i}>(value),
{I}factory
);"""
            )
            for i in class_indices
        ]

        wrap_stmts_joined = "\n\n".join(wrap_stmts)

        return Stripped(
            f"""\
{{
{I}{indent_but_first_line(const_ref_prop_type, I)} value(
{II}that->{getter_name}()
{I});

{I}{indent_but_first_line(prop_type, I)} wrapped(value);

{I}{indent_but_first_line(wrap_stmts_joined, I)}

{I}that->{setter_name}(
{II}std::move(wrapped)
{I});
}}"""
        )

    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)


# fmt: off
@require(
    lambda prop:
    isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)
)
# fmt: on
def _generate_wrap_snippet_for_optional_property(
    prop: intermediate.Property,
) -> Stripped:
    """
    Generate the snippet to recursively wrap the optional property.

    We return an empty string if there is no snippet for the property.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    setter_name = cpp_naming.setter_name(prop.name)

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        # Nothing to recurse into.
        return Stripped("")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            # Nothing to recurse into.
            return Stripped("")

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            # Nothing to recurse into.
            return Stripped("")

        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            # NOTE (mristin):
            # The non-mutating getter means here that we will not change the reference,
            # but we want to recurse into the object.
            getter_name = cpp_naming.getter_name(prop.name)

            value_type = cpp_common.generate_type(
                type_annotation=type_anno, types_namespace=Identifier("types")
            )

            value_interface_name = cpp_naming.interface_name(type_anno.our_type.name)

            return Stripped(
                f"""\
if (that->{getter_name}().has_value()) {{
{I}const {indent_but_first_line(value_type, II)}& value(
{II}that->{getter_name}().value()
{I});

{I}std::shared_ptr<
{II}types::{value_interface_name}
{I}> wrapped(
{II}Wrap<E>(
{III}value,
{III}factory
{II})
{I});

{I}that->{setter_name}(
{II}common::make_optional(
{III}std::move(wrapped)
{II})
{I});
}}"""
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(
            type_anno.items, intermediate.OurTypeAnnotation
        ) and isinstance(
            type_anno.items.our_type,
            (intermediate.AbstractClass, intermediate.ConcreteClass),
        ), (
            f"NOTE (mristin): We expect only lists of classes "
            f"at the moment, but you specified {type_anno}. "
            f"Please contact the developers if you need this feature."
        )

        getter_name = cpp_naming.getter_name(prop.name)
        value_type = cpp_common.generate_type(
            type_annotation=type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
        )

        item_type = cpp_common.generate_type_with_const_ref_if_applicable(
            type_annotation=type_anno.items, types_namespace=cpp_common.TYPES_NAMESPACE
        )

        return Stripped(
            f"""\
if (that->{getter_name}().has_value()) {{
{I}const {indent_but_first_line(value_type, II)}& value(
{II}that->{getter_name}().value()
{I});
{I}const std::size_t size = value.size();

{I}{indent_but_first_line(value_type, I)} wrapped;
{I}wrapped.reserve(size);

{I}for (
{II}{indent_but_first_line(item_type, II)} item
{II}: value
{I}) {{
{II}wrapped.emplace_back(
{III}Wrap<E>(
{IIII}item,
{IIII}factory
{III})
{II});
{I}}}

{I}that->{setter_name}(
{II}common::make_optional(
{III}std::move(wrapped)
{II})
{I});
}}"""
        )
    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        class_indices = []  # type: List[int]
        for i, item_type_anno in enumerate(type_anno.items):
            assert isinstance(
                item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                "Tuple items are restricted to atomic types (primitives, "
                "constrained primitives, classes and enumerations) by "
                "intermediate._translate._verify_only_simple_type_patterns, so no "
                "nested optionals, lists or tuples are expected here."
            )

            if isinstance(
                item_type_anno, intermediate.OurTypeAnnotation
            ) and isinstance(
                item_type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                class_indices.append(i)

        if len(class_indices) == 0:
            # Nothing to recurse into.
            return Stripped("")

        getter_name = cpp_naming.getter_name(prop.name)

        value_type = cpp_common.generate_type(
            type_annotation=type_anno, types_namespace=cpp_common.TYPES_NAMESPACE
        )

        wrap_stmts = [
            Stripped(
                f"""\
std::get<{i}>(wrapped) = Wrap<E>(
{I}std::get<{i}>(value),
{I}factory
);"""
            )
            for i in class_indices
        ]

        wrap_stmts_joined = "\n\n".join(wrap_stmts)

        return Stripped(
            f"""\
if (that->{getter_name}().has_value()) {{
{I}const {indent_but_first_line(value_type, II)}& value(
{II}that->{getter_name}().value()
{I});

{I}{indent_but_first_line(value_type, I)} wrapped(value);

{I}{indent_but_first_line(wrap_stmts_joined, I)}

{I}that->{setter_name}(
{II}common::make_optional(
{III}std::move(wrapped)
{II})
{I});
}}"""
        )
    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)


def _generate_concrete_wrap(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the concrete wrapping function for the concrete class."""
    recurse_blocks = []  # type: List[Stripped]
    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            recurse_block = _generate_wrap_snippet_for_optional_property(
                prop=prop,
            )
        else:
            recurse_block = _generate_wrap_snippet_for_required_property(
                prop=prop,
            )

        if len(recurse_block) != 0:
            recurse_blocks.append(recurse_block)

    recurse_blocks_joined = Stripped(
        "\n\n".join(recurse_blocks)
        if len(recurse_blocks) > 0
        else "// No properties to be recursively enhanced."
    )

    interface_name = cpp_naming.interface_name(cls.name)
    enhanced_cls_name = cpp_naming.class_name(Identifier(f"enhanced_{cls.name}"))

    blocks = [
        Stripped(
            """\
// We assume that we already checked whether `that` has been enhanced
// in the caller."""
        ),
        recurse_blocks_joined,
        Stripped(
            f"""\
std::shared_ptr<E> enh(
{I}factory(that)
);
return (enh == nullptr)
{I}? that
{I}: std::shared_ptr<types::{interface_name}>(
{II}new {enhanced_cls_name}<E>(
{III}that,
{III}enh
{II})
{I});"""
        ),
    ]

    body = "\n\n".join(blocks)

    function_name = cpp_naming.function_name(Identifier(f"wrap_{cls.name}"))

    return Stripped(
        f"""\
/**
 * Wrap \\p that with an enhanced instance.
 *
 * \\param that instance to be wrapped and enhanced
 * \\param factory to produce an enhancement based on an instance
 * \\return Enhanced instance, or `that` if no enhancement produced
 *
 * \\tparam E type of the enhancement
 */
template<typename E>
std::shared_ptr<types::{interface_name}> {function_name}(
{I}const std::shared_ptr<types::{interface_name}>& that,
{I}const std::function<
{II}std::shared_ptr<E>(
{III}const std::shared_ptr<types::IClass>&
{II})
{I}>& factory
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_wrap_for(
    interface_name: Identifier, concrete_classes: Sequence[intermediate.ConcreteClass]
) -> Stripped:
    """
    Generate the wrap function for the given interface.

    We do not operate on ``intermediate.Class`` directly as we also want to
    handle the case for the most abstract ``IClass``.
    """
    model_type_name = cpp_naming.enum_name(Identifier("Model_type"))

    case_blocks = []  # type: List[Stripped]
    for cls in concrete_classes:
        literal = cpp_naming.enum_literal_name(literal_name=cls.name)

        concrete_wrap_function = cpp_naming.function_name(
            Identifier(f"wrap_{cls.name}")
        )

        concrete_interface_name = cpp_naming.interface_name(cls.name)

        if concrete_interface_name == interface_name:
            case_blocks.append(
                Stripped(
                    f"""\
case types::{model_type_name}::{literal}:
{I}return impl::{concrete_wrap_function}<E>(
{II}that,
{II}factory
{I});
{I}break;"""
                )
            )
        else:
            case_blocks.append(
                Stripped(
                    f"""\
case types::{model_type_name}::{literal}:
{I}return impl::{concrete_wrap_function}<E>(
{II}std::dynamic_pointer_cast<
{III}types::{concrete_interface_name}
{II}>(that),
{II}factory
{I});
{I}break;"""
                )
            )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Unexpected model type: ",
{III}std::to_string(
{IIII}static_cast<std::uint32_t>(
{IIIII}that->model_type()
{IIII})
{III})
{II})
{I});
{I}break;"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    # noinspection SpellCheckingInspection
    body = Stripped(
        f"""\
impl::AssertNotEnhanced<
{I}E,
{I}types::{interface_name}
>(that);

switch (that->model_type()) {{
{I}{indent_but_first_line(case_blocks_joined, I)}
}}"""
    )

    function_name = cpp_naming.function_name(Identifier("wrap"))

    return Stripped(
        f"""\
template <typename E>
std::shared_ptr<
{I}types::{interface_name}
> {function_name}(
{I}const std::shared_ptr<
{II}types::{interface_name}
{I}>& that,
{I}const std::function<
{II}std::shared_ptr<E>(
{III}const std::shared_ptr<types::IClass>&
{II})
{I}>& factory
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_wrap(symbol_table: intermediate.SymbolTable) -> List[Stripped]:
    """Generate all the overloads of the main wrapping function."""
    blocks = [
        _generate_wrap_for(
            interface_name=Identifier("IClass"),
            concrete_classes=symbol_table.concrete_classes,
        )
    ]  # type: List[Stripped]

    for cls in symbol_table.classes:
        interface_name = cpp_naming.interface_name(cls.name)

        concrete_classes = []  # type: List[intermediate.ConcreteClass]
        if isinstance(cls, intermediate.ConcreteClass):
            concrete_classes.append(cls)

        concrete_classes.extend(cls.concrete_descendants)

        blocks.append(
            _generate_wrap_for(
                interface_name=interface_name, concrete_classes=concrete_classes
            )
        )

    return [
        Stripped(
            """\
/**
 * Wrap \\p that instance recursively with the enhancement produced by the \\p factory.
 *
 * The factory decides itself whether it will produce an enhancement for
 * \\p that instance, or not. Even if no enhancement has been produced for \\p that
 * instance, we will still continue to enhance the instances referenced
 * by \\p that instance recursively.
 *
 * \\param that instance to wrap
 * \\param factory to selectively produce an enhancement
 * \\return enhanced \\p that instance
 * \\throw std::logic_error if \\p that instance has been already wrapped.
 * \\tparam E type of the enhancement
 */
///@{"""
        ),
        *blocks,
        Stripped("///@}}"),
    ]


def _generate_unwrap() -> Stripped:
    """Generate the main unwrapping function."""
    function_name = cpp_naming.function_name(Identifier("unwrap"))

    body = Stripped(
        f"""\
const std::shared_ptr<impl::IEnhanced<E> >& maybe_enhanced(
{I}std::dynamic_pointer_cast<impl::IEnhanced<E> >(that)
);

if (!maybe_enhanced) {{
{I}return nullptr;
}}

return maybe_enhanced->enhancement();"""
    )

    return Stripped(
        f"""\
/**
 * Try to unwrap the enhancement from \\p that instance.
 *
 * \\param that instance possibly wrapped with an enhancement
 * \\return the enhancement, or `nullptr` if \\p that instance has not been wrapped
 * \\tparam E type of the enhancement
 */
template <typename E>
std::shared_ptr<E> {function_name}(
{I}const std::shared_ptr<types::IClass>& that
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_must_unwrap() -> Stripped:
    """Generate the main unwrapping function which throws if no enhancement present."""
    unwrap_name = cpp_naming.function_name(Identifier("unwrap"))
    function_name = cpp_naming.function_name(Identifier("must_unwrap"))

    enhancement_var = cpp_naming.variable_name(Identifier("enhancement"))

    model_type_getter = cpp_naming.getter_name(Identifier("model_type"))

    body = Stripped(
        f"""\
std::shared_ptr<E> {enhancement_var}(
{I}{unwrap_name}<E>(that)
);
if (!{enhancement_var}) {{
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Expected an instance of ",
{III}stringification::to_string(that->{model_type_getter}()),
{III}" to have been already wrapped with an enhancement, "
{III}"but it has been not."
{II})
{I});
}}
return {enhancement_var};"""
    )

    return Stripped(
        f"""\
/**
 * Unwrap the enhancement from \\p that instance.
 *
 * \\remark \\p that instance must have been wrapped before.
 *
 * \\param that instance expected to be wrapped with an enhancement
 * \\return the enhancement
 * \\throw std::invalid_argument if \\p that instance has not been wrapped
 * \\tparam E type of the enhancement
 */
template <typename E>
std::shared_ptr<E> {function_name}(
{I}const std::shared_ptr<types::IClass>& that
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(
    symbol_table: intermediate.SymbolTable,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate header for enhancing model classes."""
    namespace = Stripped(f"{library_namespace}::enhancing")

    include_guard_var = cpp_common.include_guard_var(namespace)

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/stringification.hpp"
#include "{include_prefix_path}/types.hpp"

#pragma warning(push, 0)
#include <sstream>
#include <stdexcept>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            """\
/**
 * \\defgroup enhancing Enhance instances of the model with your custom enhancements.
 * @{
 */
namespace enhancing {"""
        ),
        Stripped("// region Forward declarations"),
        *_generate_wrap_forward_declarations(symbol_table=symbol_table),
        Stripped("// endregion Forward declarations"),
        Stripped(
            """\
/// \\cond HIDDEN
namespace impl {"""
        ),
        _generate_enhanced_interface_definition(),
        *[_generate_enhanced_class(cls) for cls in symbol_table.concrete_classes],
        *[_generate_concrete_wrap(cls=cls) for cls in symbol_table.concrete_classes],
        Stripped(
            f"""\
/**
 * Assert that the \\p that instance has not been already enhanced.
 *
 * \\param that instance to be checked
 * \\tparam E type of the enhancement
 * \\tparam T interface type of \\p that instance
 * \\throw std::logic_error if \\p that already enhanced
 */
template<
{I}typename E,
{I}typename T,
{I}typename std::enable_if<
{II}std::is_base_of<types::IClass, T>::value
{I}>::type* = nullptr
>
void AssertNotEnhanced(
{I}const std::shared_ptr<T>& that
) {{
{I}std::shared_ptr<impl::IEnhanced<E> > enhanced(
{II}std::dynamic_pointer_cast<
{III}impl::IEnhanced<E>
{II}>(that)
{I});
{I}if (enhanced != nullptr) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"An instance of ",
{IIII}stringification::to_string(that->model_type()),
{IIII}" has been already wrapped."
{III})
{II});
{I}}}
}}"""
        ),
        Stripped(
            """\
}  // namespace impl
/// \\endcond"""
        ),
        *_generate_wrap(symbol_table),
        _generate_unwrap(),
        _generate_must_unwrap(),
        Stripped(
            """\
}  // namespace enhancing
/**@}*/"""
        ),
        cpp_common.generate_namespace_closing(library_namespace),
        cpp_common.WARNING,
        Stripped(f"#endif  // {include_guard_var}"),
    ]

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)
