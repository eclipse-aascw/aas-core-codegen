"""Generate code for enhancing model classes."""

import io
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
from aas_core_codegen.golang import common as golang_common, naming as golang_naming
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


@require(lambda cls, method: id(method) in cls.method_id_set)
def _generate_method_delegation(
    cls: intermediate.ConcreteClass, method: intermediate.Method
) -> Stripped:
    """Generate the delegated method to ``instance``."""
    returns = (
        golang_common.generate_type(
            method.returns, types_package=Identifier("aastypes")
        )
        if method.returns is not None
        else None
    )

    returns_suffix = "" if returns is None else f" {returns}"

    arg_types_names = [
        (
            golang_common.generate_type(
                arg.type_annotation, types_package=Identifier("aastypes")
            ),
            golang_naming.argument_name(arg.name),
        )
        for arg in method.arguments
    ]

    method_name = golang_naming.method_name(method.name)

    return_prefix = "return " if method.returns is not None else ""

    struct_name = golang_naming.private_struct_name(Identifier(f"enhanced_{cls.name}"))
    receiver = golang_naming.receiver_name(cls)

    if len(method.arguments) == 0:
        return Stripped(
            f"""\
func ({receiver} *{struct_name}[E]) {method_name}(){returns_suffix} {{
{I}{return_prefix}{receiver}.instance.{method_name}()
}}"""
        )

    arguments_definition = ",".join(
        f"{arg_name} {arg_type}," for arg_type, arg_name in arg_types_names
    )

    arguments_delegation = "\n".join(f"{arg_name}," for _, arg_name in arg_types_names)

    return Stripped(
        f"""\
func ({receiver} *{struct_name}[E]) {method_name}(
{I}{indent_but_first_line(arguments_definition, I)}
){returns_suffix} {{
{I}{return_prefix}{receiver}.instance.{method_name}(
{II}{indent_but_first_line(arguments_delegation, II)}
{I})
}}"""
    )


def _generate_enhanced_struct_and_its_methods(
    cls: intermediate.ConcreteClass,
) -> List[Stripped]:
    """Generate the `enhanced*` struct and its methods as delegation to ``instance``."""
    enhanced_struct_name = golang_naming.private_struct_name(
        Identifier(f"Enhanced_{cls.name}")
    )
    interface_name = golang_naming.interface_name(cls.name)

    model_type_enum = golang_naming.enum_name(Identifier("Model_type"))
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))

    # NOTE (mristin):
    # Add an "e" prefix to signal that it is enhanced.
    receiver = golang_naming.receiver_name(cls, prefix="enhanced_")

    result = [
        Stripped(
            f"""\
type {enhanced_struct_name}[E any] struct {{
{I}instance aastypes.{interface_name}
{I}enhancement E
}}"""
        ),
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) {model_type_getter}(
) aastypes.{model_type_enum} {{
{I}return {receiver}.instance.{model_type_getter}()
}}"""
        ),
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) DescendOnce(
{I}action func(aastypes.IClass)bool,
) bool {{
{I}return {receiver}.instance.DescendOnce(action)
}}"""
        ),
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) Descend(
{I}action func(aastypes.IClass) bool,
) bool {{
{I}return {receiver}.instance.Descend(action)
}}"""
        ),
    ]

    for prop in cls.properties:
        prop_type = golang_common.generate_type(
            type_annotation=prop.type_annotation, types_package=Identifier("aastypes")
        )

        getter_name = golang_naming.getter_name(prop.name)
        result.append(
            Stripped(
                f"""\
func ({receiver} *{enhanced_struct_name}[E]) {getter_name}(
) {prop_type} {{
{I}return {receiver}.instance.{getter_name}()
}}"""
            )
        )

        setter_name = golang_naming.setter_name(prop.name)
        result.append(
            Stripped(
                f"""\
func ({receiver} *{enhanced_struct_name}[E]) {setter_name}(
{I}value {prop_type},
) {{
{I}{receiver}.instance.{setter_name}(value)
}}"""
            )
        )

    for method in cls.methods:
        result.append(_generate_method_delegation(cls=cls, method=method))

    result.append(
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) getEnhancement(
) E {{
{I}return {receiver}.enhancement
}}"""
        )
    )

    result.append(
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) setEnhancement(
{I}value E,
) {{
{I}{receiver}.enhancement = value
}}"""
        )
    )

    return result


def _generate_wrap_for_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the wrapping function for the concrete class."""
    interface_name = golang_naming.interface_name(cls.name)
    function_name = golang_naming.private_function_name(Identifier(f"wrap_{cls.name}"))

    enhanced_struct_name = golang_naming.private_struct_name(
        Identifier(f"enhanced_{cls.name}")
    )

    recurse_blocks = []  # type: List[Stripped]
    for prop in cls.properties:
        recurse_block: Stripped

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_getter_name = golang_naming.getter_name(prop.name)
        prop_setter_name = golang_naming.setter_name(prop.name)

        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
            # Nothing to recurse into.
            continue

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                # Nothing to recurse into.
                continue

            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                # Nothing to recurse into.
                continue

            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                prop_interface_name = golang_naming.interface_name(
                    type_anno.our_type.name
                )
                recurse_block = Stripped(
                    f"""\
that.{prop_setter_name}(
{I}Wrap[E](
{II}{prop_var},
{II}factory,
{I}).(aastypes.{prop_interface_name}),
)"""
                )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
                # Nothing to recurse into.
                continue

            elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                    # Nothing to recurse into.
                    continue

                elif isinstance(
                    type_anno.items.our_type, intermediate.ConstrainedPrimitive
                ):
                    # Nothing to recurse into.
                    continue

                elif isinstance(
                    type_anno.items.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    items_interface_name = golang_naming.interface_name(
                        type_anno.items.our_type.name
                    )

                    recurse_block = Stripped(
                        f"""\
for i, v := range {prop_var} {{
{I}// Update in-situ
{I}{prop_var}[i] = Wrap[E](
{II}v,
{II}factory,
{I}).(aastypes.{items_interface_name})
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
            item_assignments = []  # type: List[Stripped]
            for i, item_type_anno in enumerate(type_anno.items):
                if not (
                    isinstance(item_type_anno, intermediate.OurTypeAnnotation)
                    and isinstance(
                        item_type_anno.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    )
                ):
                    continue

                item_interface_name = golang_naming.interface_name(
                    item_type_anno.our_type.name
                )

                item_assignments.append(
                    Stripped(
                        f"""\
{prop_var}.Item{i + 1} = Wrap[E](
{I}{prop_var}.Item{i + 1},
{I}factory,
).(aastypes.{item_interface_name})"""
                    )
                )

            if len(item_assignments) == 0:
                continue

            item_assignments_joined = "\n".join(item_assignments)
            recurse_block = Stripped(
                f"""\
{item_assignments_joined}
that.{prop_setter_name}(
{I}{prop_var},
)"""
            )

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            recurse_block = Stripped(
                f"""\
{prop_var} := that.{prop_getter_name}()
if {prop_var} != nil {{
{I}{indent_but_first_line(recurse_block, I)}
}}"""
            )
        else:
            recurse_block = Stripped(
                f"""\
{prop_var} := that.{prop_getter_name}()
{recurse_block}"""
            )

        recurse_blocks.append(recurse_block)

    blocks = [
        Stripped(
            """\
// We assume that we already checked whether `that` has been enhanced
// in the caller."""
        ),
        Stripped(
            f"""\
enh, shouldEnhance := factory(that)
if shouldEnhance {{
{I}result = &{enhanced_struct_name}[E]{{
{II}instance: that,
{II}enhancement: enh,
{I}}}
}} else {{
{I}result = that
}}"""
        ),
    ]

    if len(recurse_blocks) > 0:
        blocks.extend(recurse_blocks)

    blocks.append(Stripped("return"))

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
func {function_name}[E any](
{I}that aastypes.{interface_name},
{I}factory func(aastypes.IClass) (E, bool),
) (result aastypes.{interface_name}) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_wrap(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the `Wrap` function."""
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))
    blocks = [
        Stripped(
            f"""\
_, ok := that.(enhanced[E])
if ok {{
{I}panic(
{II}fmt.Sprintf(
{III}"An instance of %T has been already wrapped: %v",
{III}that, that,
{II}),
{I})
}}"""
        )
    ]  # type: List[Stripped]

    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        interface_name = golang_naming.interface_name(cls.name)
        wrap_function = golang_naming.private_function_name(
            Identifier(f"wrap_{cls.name}")
        )

        case_blocks.append(
            Stripped(
                f"""\
case aastypes.{literal}:
{I}result = {wrap_function}[E](
{II}that.(aastypes.{interface_name}),
{II}factory,
{I})"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}panic(
{II}fmt.Sprintf(
{III}"Unexpected model type: %v",
{III}that.{model_type_getter}(),
{II}),
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)
    blocks.append(
        Stripped(
            f"""\
switch that.{model_type_getter}() {{
{case_blocks_joined}
}}"""
        )
    )

    blocks.append(Stripped("return"))

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
// Wrap `that` instance recursively with the enhancement produced by the `factory`.
//
// The factory returns the enhancement, and a boolean "should-enhance". If
// the "should-enhance" is false, `that` instance is not enhance, and we simply
// return it. However, we will still continue to enhance the instances referenced
// by `that` instance recursively.
//
// If `that` instance has been already wrapped, panic.
func Wrap[E any](
{I}that aastypes.IClass,
{I}factory func(aastypes.IClass) (E, bool),
) (result aastypes.IClass) {{
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
def generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for enhancing model classes."""
    errors = []  # type: List[Error]

    aastypes_url_literal = golang_common.string_literal(f"{repo_url}/types")
    aascommon_url_literal = golang_common.string_literal(f"{repo_url}/common")

    blocks = [
        Stripped(
            """\
// Package enhancing allows for enhancement of model instances with your custom data.
package enhancing"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"fmt"

{I}aascommon {aascommon_url_literal}
{I}aastypes {aastypes_url_literal}
)"""
        ),
        Stripped(
            f"""\
type enhanced[E any] interface {{
{I}// Get the enhancement from the enhanced instance.
{I}getEnhancement() E

{I}// Set the enhancement of the enhanced instance.
{I}setEnhancement(E)
}}"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            implementation_key = specific_implementations.ImplementationKey(
                f"Enhancing/{cls.name}.go"
            )

            implementation = spec_impls.get(implementation_key, None)
            if implementation is None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The enhancing snippet is missing "
                        f"for the implementation-specific "
                        f"class {cls.name}: {implementation_key}",
                    )
                )
                continue
        else:
            blocks.extend(_generate_enhanced_struct_and_its_methods(cls=cls))
            blocks.append(_generate_wrap_for_cls(cls=cls))

    blocks.append(_generate_wrap(symbol_table=symbol_table))
    blocks.extend(
        [
            Stripped(
                f"""\
// Retrieve the enhancement from `that` instance.
//
// Return the enhancement, or `ok` false, if `that` instance has not been
// enhanced.
func Unwrap[E any](that aastypes.IClass) (enhancement E, ok bool) {{
{I}var enh enhanced[E]
{I}enh, ok = that.(enhanced[E])
{I}if !ok {{
{II}return
{I}}}
{I}enhancement = enh.getEnhancement()
{I}return
}}"""
            ),
            Stripped(
                f"""\
// Retrieve the enhancement from `that` instance.
//
// If `that` instance has not been enhanced yet, panic.
func MustUnwrap[E any](that aastypes.IClass) (enhancement E) {{
{I}var ok bool
{I}enhancement, ok = Unwrap[E](that)
{I}if !ok {{
{II}panic(
{III}fmt.Sprintf(
{IIII}"An instance of %T has not been wrapped: %v",
{IIII}that, that,
{III}),
{II})
{I}}}
{I}return
}}"""
            ),
            golang_common.WARNING,
        ]
    )

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
