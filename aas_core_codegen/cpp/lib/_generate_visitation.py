"""Generate code of visitors to iterate over instances."""

import io
from typing import (
    List,
    Tuple,
)

from icontract import ensure

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Identifier,
    assert_never,
    Stripped,
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
)

# region Generation


def _generate_mutating_visitor_interface(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the interface for a mutating visitor."""
    visit_methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        method_name = cpp_naming.method_name(Identifier(f"visit_{cls.name}"))
        that_type = cpp_naming.interface_name(cls.name)

        visit_methods.append(
            Stripped(
                f"""\
virtual void {method_name}(
{I}const std::shared_ptr<types::{that_type}>& that
) = 0;"""
            )
        )

    visit_methods_joined = "\n".join(visit_methods)

    return Stripped(
        f"""\
/**
 * Provide an interface for a recursive mutating visitor on an instance.
 */
class IVisitor {{
 public:
{I}/**
{I} * Visit \\p that instance and recursively visit all the instances
{I} * referenced from \\p that instance.
{I} *
{I} * We use const references to shared pointers here for efficiency in case you want,
{I} * say, to share ownership over instances in your own external containers. Since
{I} * we do not make copies of the shared pointers, it is very important that
{I} * the given shared pointers outlive the visitor, lest cause undefined behavior.
{I} * See these StackOverflow questions:
{I} * * https://stackoverflow.com/questions/12002480/passing-stdshared-ptr-to-constructors/12002668#12002668
{I} * * https://stackoverflow.com/questions/3310737/should-we-pass-a-shared-ptr-by-reference-or-by-value
{I} * * https://stackoverflow.com/questions/37610494/passing-const-shared-ptrt-versus-just-shared-ptrt-as-parameter
{I} *
{I} * Changing the references during the visitation results in undefined
{I} * behavior. This follows how STL deals with modifications to containers, see:
{I} * https://stackoverflow.com/questions/6438086/iterator-invalidation-rules-for-c-containers
{I} *
{I} * \\param that instance to be visited recursively
{I} */
{I}virtual void Visit(const std::shared_ptr<types::IClass>& that) = 0;
{I}virtual ~IVisitor() = default;

 protected:
{I}{indent_but_first_line(visit_methods_joined, I)}
}};  // class IVisitor"""
    )


def _generate_mutating_abstract_visitor_definition() -> Stripped:
    """Generate the definition of an abstract mutating visitor."""
    return Stripped(
        f"""\
/**
 * Provide an abstract recursive mutating visitor on an instance.
 */
class AbstractVisitor
{II}: public IVisitor {{
 public:
{I}void Visit(const std::shared_ptr<types::IClass>& that) override;
{I}~AbstractVisitor() override = default;
}};  // class AbstractVisitor"""
    )


def _generate_mutating_pass_through_visitor_definition(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the definition of a no-op mutating visitor."""
    visit_methods = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        method_name = cpp_naming.method_name(Identifier(f"visit_{cls.name}"))
        that_type = cpp_naming.interface_name(cls.name)
        visit_methods.append(
            Stripped(
                f"""\
void {method_name}(
{I}const std::shared_ptr<types::{that_type}>& that
) override;"""
            )
        )

    visit_methods_joined = "\n".join(visit_methods)

    return Stripped(
        f"""\
/**
 * \\brief Provide a mutating, recursive and no-op visitor on an instance.
 *
 * Usually, you want to inherit from this visitor and override one or more of its
 * visitation methods.
 */
class PassThroughVisitor
{II}: public AbstractVisitor {{
 public:
{I}~PassThroughVisitor() override = default;

 protected:
{I}{indent_but_first_line(visit_methods_joined, I)}
}};  // class PassThroughVisitor"""
    )


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_header(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate header of visitors to iterate over instances."""
    namespace = Stripped(f"{library_namespace}::visitation")

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
            f'''\
#include "{include_prefix_path}/types.hpp"'''
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            """\
/**
 * \\defgroup visitation Iterate and modify instances through visitors.
 * @{
 */
namespace visitation {"""
        ),
        _generate_mutating_visitor_interface(symbol_table=symbol_table),
        _generate_mutating_abstract_visitor_definition(),
        _generate_mutating_pass_through_visitor_definition(symbol_table=symbol_table),
    ]  # type: List[Stripped]

    blocks.extend(
        [
            Stripped(
                """\
}  // namespace visitation
/**@*/"""
            ),
            cpp_common.generate_namespace_closing(library_namespace),
            cpp_common.WARNING,
            Stripped(f"#endif  // {include_guard_var}"),
        ]
    )

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue()


def _generate_dispatching_visit_switch_statement(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the dispatching statement for the visitor's main ``Visit`` method."""
    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        model_type_literal = cpp_naming.enum_literal_name(cls.name)
        visit_name = cpp_naming.method_name(Identifier(f"visit_{cls.name}"))
        interface_name = cpp_naming.interface_name(cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case types::ModelType::{model_type_literal}:
{I}{visit_name}(
{II}std::dynamic_pointer_cast<
{III}types::{interface_name}
{II}>(that)
{I});
{I}break;"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::logic_error(
{II}common::Concat(
{III}"Unexpected model type: ",
{III}std::to_string(
{IIII}static_cast<std::uint32_t>(that->model_type())
{III})
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    switch_stmt = Stripped(
        f"""\
// NOTE (mristin):
// We have to dynamically cast the pointers due to the virtual multiple
// inheritance, and also because we used shared pointers for references.
// If we used constant references instead of shared pointers, we could use
// a pattern such as double dispatch. However, this has the limitation that
// it would prevent us from collecting the instances in the visitor, such that
// they outlive the original structures.

switch (that->model_type()) {{
{I}{indent_but_first_line(case_blocks_joined, I)}
}}"""
    )

    return switch_stmt


def _generate_mutating_abstract_visitor_implementation(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate implementation of the visitor's method(s)."""
    switch_stmt = _generate_dispatching_visit_switch_statement(
        symbol_table=symbol_table
    )

    blocks = [
        Stripped("// region AbstractVisitor"),
        Stripped(
            f"""\
void AbstractVisitor::Visit(
{I}const std::shared_ptr<types::IClass>& that
) {{
{I}{indent_but_first_line(switch_stmt, I)}
}}"""
        ),
        Stripped("// endregion"),
    ]  # type: List[Stripped]

    return blocks


def _generate_recursive_visit_for_property(
    prop: intermediate.Property, mutating: bool
) -> Stripped:
    """
    Generate the snippet to visit a property recursively.

    Empty result means the property can not be descended into.

    If ``mutating`` is set, use the mutable getter.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    getter = (
        cpp_naming.mutable_getter_name(prop.name)
        if mutating
        else cpp_naming.getter_name(prop.name)
    )

    if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        maybe_var = cpp_naming.variable_name(Identifier(f"maybe_{prop.name}"))
        get_expr = Stripped(f"{maybe_var}.value()")
    else:
        get_expr = Stripped(f"that->{getter}()")

    code: Stripped

    if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
        # No visits to primitive values.
        return Stripped("")

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.Enumeration):
            # No visits to enumerations.
            return Stripped("")

        elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
            # No visits to primitive values.
            return Stripped("")

        elif isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            code = Stripped(
                f"""\
Visit(
{I}{get_expr}
);"""
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_anno.our_type)
    elif isinstance(type_anno, intermediate.ListTypeAnnotation):
        if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
            # No visits to primitive values.
            return Stripped("")

        elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                # No visits to enumerations.
                return Stripped("")

            elif isinstance(
                type_anno.items.our_type, intermediate.ConstrainedPrimitive
            ):
                # No visits to primitive values.
                return Stripped("")

            elif isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                item_type = cpp_common.generate_type_with_const_ref_if_applicable(
                    type_annotation=type_anno.items,
                    types_namespace=cpp_common.TYPES_NAMESPACE,
                )

                code = Stripped(
                    f"""\
for (
{I}{indent_but_first_line(item_type, I)} item :
{I}{indent_but_first_line(get_expr, I)}
) {{
{I}Visit(item);
}}"""
                )
            else:
                assert_never(type_anno.items.our_type)

        else:
            raise NotImplementedError(
                "NOTE (mristin): We currently generate the visitation only for "
                f"lists of atomic values, but you provided {prop.type_annotation}. "
                f"Please contact the developers if you need this feature."
            )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        visit_stmts = []  # type: List[Stripped]
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
                visit_stmts.append(
                    Stripped(
                        f"""\
Visit(
{I}std::get<{i}>(
{II}{indent_but_first_line(get_expr, II)}
{I})
);"""
                    )
                )

        if len(visit_stmts) == 0:
            # No visits to any of the tuple items.
            return Stripped("")

        code = Stripped("\n".join(visit_stmts))

    else:
        # noinspection PyTypeChecker
        assert_never(type_anno)

    if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
        return Stripped(
            f"""\
// {getter}
{code}"""
        )

    maybe_var = cpp_naming.variable_name(Identifier(f"maybe_{prop.name}"))
    maybe_type = cpp_common.generate_type_with_const_ref_if_applicable(
        type_annotation=prop.type_annotation, types_namespace=cpp_common.TYPES_NAMESPACE
    )

    return Stripped(
        f"""\
// region {getter}
{maybe_type} {maybe_var}(
{I}that->{getter}()
);
if ({maybe_var}.has_value()) {{
{I}{indent_but_first_line(code, I)}
}}
// endregion"""
    )


def _generate_pass_through_visit_body_for_class(
    cls: intermediate.ConcreteClass, mutating: bool
) -> Tuple[Stripped, bool]:
    """
    Generate the body of a pass-through visit member.

    If ``mutating`` is set, the pass-through is mutating.

    Return (code, True if any of the properties will be recursively visited)
    """
    blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        code = _generate_recursive_visit_for_property(prop=prop, mutating=mutating)
        if code != "":
            blocks.append(code)

    if len(blocks) == 0:
        return Stripped("// No properties to be passed through."), False

    return Stripped("\n\n".join(blocks)), True


def _generate_mutating_pass_through_visitor_implementation(
    symbol_table: intermediate.SymbolTable,
) -> List[Stripped]:
    """Generate implementation of the visitor's method(s)."""
    blocks = [
        Stripped("// region PassThroughVisitor"),
    ]

    for cls in symbol_table.concrete_classes:
        body, is_recursive = _generate_pass_through_visit_body_for_class(
            cls=cls, mutating=True
        )
        method_name = cpp_naming.method_name(Identifier(f"visit_{cls.name}"))
        that_type = cpp_naming.interface_name(cls.name)

        if is_recursive:
            blocks.append(
                Stripped(
                    f"""\
void PassThroughVisitor::{method_name}(
{I}const std::shared_ptr<types::{that_type}>& that
) {{
{I}{indent_but_first_line(body, I)}
}}"""
                )
            )
        else:
            # NOTE (mristin):
            # We need to signal to the compiler that this function does nothing, and
            # that we will not use the argument. Note that ``that`` is only used if
            # there is further recursion, see above in the if-body.
            blocks.append(
                Stripped(
                    f"""\
void PassThroughVisitor::{method_name}(
{I}const std::shared_ptr<types::{that_type}>&
) {{
{I}{indent_but_first_line(body, I)}
}}"""
                )
            )

    blocks.append(Stripped("// endregion"))

    return blocks


# fmt: off
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """Generate implementation of visitors to iterate over instances."""
    namespace = Stripped(f"{library_namespace}::visitation")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/types.hpp"
#include "{include_prefix_path}/stringification.hpp"
#include "{include_prefix_path}/visitation.hpp"

#pragma warning(push, 0)
#include <sstream>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        *_generate_mutating_abstract_visitor_implementation(symbol_table=symbol_table),
        *_generate_mutating_pass_through_visitor_implementation(
            symbol_table=symbol_table
        ),
    ]  # type: List[Stripped]

    blocks.extend(
        [
            cpp_common.generate_namespace_closing(namespace),
            cpp_common.WARNING,
        ]
    )

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


# endregion


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
