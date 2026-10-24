"""Generate code for enhancing model classes."""

import io
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
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    pointering as golang_pointering,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


@require(lambda cls, method: intermediate.runtime_id(method) in cls.method_id_set)
def _generate_method_delegation(
    cls: intermediate.ConcreteClass, method: intermediate.Method
) -> Stripped:
    """Generate the delegated method to ``instance``."""
    returns = (
        golang_common.generate_type(
            method.returns, types_package=Identifier("ourtypes")
        )
        if method.returns is not None
        else None
    )

    returns_suffix = "" if returns is None else f" {returns}"

    arg_types_names = [
        (
            golang_common.generate_type(
                arg.type_annotation, types_package=Identifier("ourtypes")
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

    arguments_definition = "\n".join(
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
{I}instance ourtypes.{interface_name}
{I}enhancement E
}}"""
        ),
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) {model_type_getter}(
) ourtypes.{model_type_enum} {{
{I}return {receiver}.instance.{model_type_getter}()
}}"""
        ),
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) DescendOnce(
{I}action func(ourtypes.IClass)bool,
) bool {{
{I}return {receiver}.instance.DescendOnce(action)
}}"""
        ),
        Stripped(
            f"""\
func ({receiver} *{enhanced_struct_name}[E]) Descend(
{I}action func(ourtypes.IClass) bool,
) bool {{
{I}return {receiver}.instance.Descend(action)
}}"""
        ),
    ]

    for prop in cls.properties:
        prop_type = golang_common.generate_type(
            type_annotation=prop.type_annotation, types_package=Identifier("ourtypes")
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
        if method.visibility is not intermediate.Visibility.PUBLIC:
            continue

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


def _wrap_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the function wrapping in-situ the instances held by ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.golang.common.type_moniker`), so two different
    containers never share a function. The other functions of the package never
    contain an underscore, so they can not collide with it either. No leaf moniker
    is ``inPlace``, so the suffix keeps the names injective.
    """
    return Identifier(f"wrap_{golang_common.type_moniker(type_anno)}_inPlace")


def _generate_wrap_call(name: str, arg: str) -> Stripped:
    """Generate the call of the wrapping function ``name`` on ``arg``."""
    # Heuristic to break the lines, very rudimentary
    if len(name) + len(arg) > 50:
        return Stripped(
            f"""\
{name}[E](
{I}{arg},
{I}factory,
)"""
        )

    return Stripped(f"{name}[E]({arg}, factory)")


def _wrap_instance_name(type_anno: intermediate.OurTypeAnnotation) -> str:
    """Name the helper wrapping the class instance or the named union."""
    if isinstance(type_anno.our_type, intermediate.NamedUnion):
        return "wrapUnion"

    return "wrapClass"


@require(
    lambda type_anno, descendability: (
        type_anno in descendability and descendability[type_anno]
    )
)
def _generate_wrap_stmt(
    target: str,
    type_anno: intermediate.TypeAnnotationUnion,
    descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
) -> Stripped:
    """
    Generate the statement wrapping the instances held by the variable ``target``.

    An instance is replaced by its wrapper. A container is delegated to its
    function, which wraps only one level in-situ and calls the functions of its
    items by name. This way the wrapping is composed of plain functions, to any
    depth, and no container is ever copied.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        wrap_call = _generate_wrap_call(_wrap_instance_name(type_anno), target)
        return Stripped(f"{target} = {wrap_call}")

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        return _generate_wrap_call(_wrap_container_name(type_anno), target)

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        # NOTE (mristin):
        # A tuple is a struct passed by value, so we pass a pointer to it.
        return _generate_wrap_call(_wrap_container_name(type_anno), f"&{target}")

    raise AssertionError(
        f"Unexpected type annotation holding instances: {type_anno}. "
        f"The optionals nested in the containers should have been refused in "
        f"parse._translate._verify_symbol_table, and the sets "
        f"never hold instances."
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
    Generate the function wrapping in-situ the instances held by ``type_anno``.

    The ``descendability`` maps ``type_anno`` and its nested type annotations,
    see :py:func:`aas_core_codegen.intermediate.map_descendability`.
    """
    body: Stripped
    that_type: str

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_stmt = _generate_wrap_stmt(
            target="that[i]", type_anno=type_anno.items, descendability=descendability
        )

        body = Stripped(
            f"""\
for i := range that {{
{I}{indent_but_first_line(item_stmt, I)}
}}"""
        )

        that_type = golang_common.generate_type(
            type_anno, types_package=Identifier("ourtypes")
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # A set is a Golang map, and its keys can not be replaced while we iterate
        # over it. Since no set holds instances at the moment, we refuse to
        # generate the wrapping for now.
        raise AssertionError(
            f"Unexpected set holding instances: {type_anno}. We do not generate "
            f"the wrapping of sets, since the keys of a Golang map can not be "
            f"replaced in-situ. Please contact the developers if you need "
            f"this feature."
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        body = Stripped(
            "\n".join(
                _generate_wrap_stmt(
                    target=f"that.Item{i + 1}",
                    type_anno=item,
                    descendability=descendability,
                )
                for i, item in enumerate(type_anno.items)
                if descendability[item]
            )
        )

        that_type = "*" + golang_common.generate_type(
            type_anno, types_package=Identifier("ourtypes")
        )

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
// Wrap recursively the instances held by `that` in-situ.
func {_wrap_container_name(type_anno)}[E any](
{I}that {that_type},
{I}factory func(ourtypes.IClass) (E, bool),
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_wrap_for_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the wrapping function for the concrete class."""
    interface_name = golang_naming.interface_name(cls.name)
    function_name = golang_naming.private_function_name(Identifier(f"wrap_{cls.name}"))

    enhanced_struct_name = golang_naming.private_struct_name(
        Identifier(f"enhanced_{cls.name}")
    )

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

    for prop in cls.properties:
        descendability = intermediate.map_descendability(prop.type_annotation)

        if not descendability[prop.type_annotation]:
            # We can not enhance anything held by this property; nothing to do here.
            continue

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_getter_name = golang_naming.getter_name(prop.name)
        prop_setter_name = golang_naming.setter_name(prop.name)

        is_optional = isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        )

        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        stmt: Stripped
        if isinstance(type_anno, intermediate.OurTypeAnnotation):
            wrap_call = _generate_wrap_call(
                _wrap_instance_name(type_anno),
                prop_var if is_optional else f"that.{prop_getter_name}()",
            )

            stmt = Stripped(
                f"""\
that.{prop_setter_name}(
{I}{indent_but_first_line(wrap_call, I)},
)"""
            )

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            # NOTE (mristin):
            # The list is wrapped in-situ, so there is nothing to set.
            stmt = _generate_wrap_call(
                _wrap_container_name(type_anno),
                prop_var if is_optional else f"that.{prop_getter_name}()",
            )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            if is_optional:
                # NOTE (mristin):
                # An optional tuple is a pointer, so it is wrapped in-situ and
                # there is nothing to set.
                assert golang_pointering.is_pointer_type(prop.type_annotation)

                stmt = _generate_wrap_call(_wrap_container_name(type_anno), prop_var)
            else:
                # NOTE (mristin):
                # The getter returns the tuple by value, so we have to set it back.
                wrap_call = _generate_wrap_call(
                    _wrap_container_name(type_anno), f"&{prop_var}"
                )

                stmt = Stripped(
                    f"""\
{prop_var} := that.{prop_getter_name}()
{wrap_call}
that.{prop_setter_name}(
{I}{prop_var},
)"""
                )

        else:
            raise AssertionError(
                f"Unexpected type annotation holding instances: {type_anno}"
            )

        if is_optional:
            stmt = Stripped(
                f"""\
{prop_var} := that.{prop_getter_name}()
if {prop_var} != nil {{
{I}{indent_but_first_line(stmt, I)}
}}"""
            )

        blocks.append(stmt)

    blocks.append(Stripped("return"))

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
func {function_name}[E any](
{I}that ourtypes.{interface_name},
{I}factory func(ourtypes.IClass) (E, bool),
) (result ourtypes.{interface_name}) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_self_union_and_wrap_union() -> Stripped:
    """
    Generate the ``selfUnion`` constraint and the ``wrapUnion`` helper.

    A named union is not itself an ``ourtypes.IClass``, so it can not be
    passed to ``wrapClass[E]``, and its underlying instance has to be
    unwrapped, enhanced and re-wrapped. Go has no method overloading, so this
    is a sibling helper rather than an overload. ``T`` is self-bounded via
    ``selfUnion[T]``, so that we need only this one helper for *all* named
    unions, while the result still comes back as the caller's own concrete
    union type (*e.g.*, ``*ourtypes.StructuralUnion``).
    """
    return Stripped(
        f"""\
// Constrain a generic type parameter to a named union whose underlying
// instance can be re-wrapped into the same concrete union type, needed for
// a generic helper that both unwraps and re-wraps without knowing the
// concrete union type.
type selfUnion[T any] interface {{
{I}Underlying() ourtypes.IClass
{I}WithUnderlying(ourtypes.IClass) T
}}

// Wrap the underlying instance of `that` union recursively with the
// enhancement produced by `factory`, and re-wrap the result back into the
// same concrete union type as `that`.
func wrapUnion[E any, T selfUnion[T]](
{I}that T,
{I}factory func(ourtypes.IClass) (E, bool),
) T {{
{I}return that.WithUnderlying(
{II}Wrap[E](
{III}that.Underlying(),
{III}factory,
{II}),
{I})
}}"""
    )


def _generate_wrap(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the `Wrap` function."""
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))
    blocks: List[Stripped] = [
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
    ]

    case_blocks: List[Stripped] = []
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
case ourtypes.{literal}:
{I}result = {wrap_function}[E](
{II}that.(ourtypes.{interface_name}),
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
{I}that ourtypes.IClass,
{I}factory func(ourtypes.IClass) (E, bool),
) (result ourtypes.IClass) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


#: Stand in for the import block, which is filled in at the very end: it
#: depends on what the generated code actually names, and an unused import does
#: not compile in Go.
_IMPORT_PLACEHOLDER = Stripped("")


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
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for enhancing model classes."""
    ourcommon_url_literal = golang_common.string_literal(f"{repo_url}/common")

    ourtypes_url_literal = golang_common.string_literal(f"{repo_url}/types")

    blocks: List[Stripped] = [
        Stripped(
            """\
// Package enhancing allows for enhancement of model instances with your custom data.
package enhancing"""
        ),
        golang_common.WARNING,
        _IMPORT_PLACEHOLDER,
        Stripped(
            f"""\
type enhanced[E any] interface {{
{I}// Get the enhancement from the enhanced instance.
{I}getEnhancement() E

{I}// Set the enhancement of the enhanced instance.
{I}setEnhancement(E)
}}"""
        ),
    ]

    for cls in symbol_table.concrete_classes:
        blocks.extend(_generate_enhanced_struct_and_its_methods(cls=cls))
        blocks.append(_generate_wrap_for_cls(cls=cls))

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

                moniker = golang_common.type_moniker(type_anno)
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
// Wrap `that` instance recursively with the enhancement produced by
// the `factory`, and keep its static type.
func wrapClass[E any, T ourtypes.IClass](
{I}that T,
{I}factory func(ourtypes.IClass) (E, bool),
) T {{
{I}return Wrap[E](that, factory).(T)
}}"""
            )
        )

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_self_union_and_wrap_union())

    blocks.extend(container_blocks)

    blocks.append(_generate_wrap(symbol_table=symbol_table))
    blocks.extend(
        [
            Stripped(
                f"""\
// Retrieve the enhancement from `that` instance.
//
// Return the enhancement, or `ok` false, if `that` instance has not been
// enhanced.
func Unwrap[E any](that ourtypes.IClass) (enhancement E, ok bool) {{
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
func MustUnwrap[E any](that ourtypes.IClass) (enhancement E) {{
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

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines: List[str] = []
    if golang_common.names_package(blocks, "fmt"):
        import_lines.append(f'{I}"fmt"')

    if golang_common.names_package(blocks, "ourcommon"):
        import_lines.append(f"{I}ourcommon {ourcommon_url_literal}")

    import_lines.append(f"{I}ourtypes {ourtypes_url_literal}")

    blocks[import_index] = Stripped("import (\n" + "\n".join(import_lines) + "\n)")

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
