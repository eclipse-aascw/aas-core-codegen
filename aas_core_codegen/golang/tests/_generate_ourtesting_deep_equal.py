"""Generate code to perform a comparison of deep equality on instances."""

import io
from typing import List, Set

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Stripped,
    Identifier,
    indent_but_first_line,
    assert_never,
)
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    pointering as golang_pointering,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
)


def _compares_by_equality_operator(
    type_anno: intermediate.TypeAnnotationUnion,
) -> bool:
    """
    Check whether Go's ``==`` compares deeply the values of ``type_anno``.

    The primitives, the constrained primitives and the enumeration literals
    compare by value -- except for the byte slices, which Go can not compare
    with ``==`` at all. A tuple is a struct, which compares by ``==`` field by
    field, so it compares deeply as long as its items do. The slices and the
    maps can not be compared with ``==``, and the instances would be compared
    by reference.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return primitive_type is not intermediate.PrimitiveType.BYTEARRAY

    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        return isinstance(type_anno.our_type, intermediate.Enumeration)

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return all(_compares_by_equality_operator(item) for item in type_anno.items)

    return False


def _deep_equal_container_name(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Identifier:
    """
    Name the function comparing deeply ``type_anno``.

    The moniker is injective (see
    :py:func:`aas_core_codegen.golang.common.type_moniker`), so two different
    containers never share a function. The moniker contains an underscore,
    unlike a class name, so the name never collides with the function
    comparing a class.
    """
    return Identifier(f"deepEqual{golang_common.type_moniker(type_anno)}")


def _generate_unequal_condition(
    that: str, other: str, type_anno: intermediate.TypeAnnotationUnion
) -> Stripped:
    """
    Generate the condition that the values at ``that`` and ``other`` differ.

    A container which can not be compared by ``==`` is delegated to its
    function, which compares only one level and calls the function of its
    items by name. This way the deep equality is composed of plain functions,
    to any depth.
    """
    if _compares_by_equality_operator(type_anno):
        return Stripped(f"{that} != {other}")

    callee: str
    that_arg = that
    other_arg = other

    if intermediate.try_primitive_type(type_anno) is not None:
        # NOTE (mristin):
        # Only a byte slice is a primitive which is not compared by ``==``.
        callee = "bytes.Equal"

    elif isinstance(type_anno, intermediate.OurTypeAnnotation):
        if isinstance(type_anno.our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is not itself an ``IClass``, so we compare
            # the underlying instances instead.
            that_arg = f"{that}.Underlying()"
            other_arg = f"{other}.Underlying()"
        else:
            assert isinstance(
                type_anno.our_type, intermediate.Class
            ), f"Unexpected our type not compared by ==: {type_anno}"

        callee = "DeepEqual"

    elif isinstance(
        type_anno,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # A JSON-able value is an open structure of maps, slices and
        # scalars, none of which Go's ``==`` can compare, so it goes
        # through ``reflect.DeepEqual``. Every other kind of value here is
        # compared structurally instead, which is why this is the only
        # place in the module which reaches for reflection.
        callee = "reflect.DeepEqual"

    elif isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple):
        callee = _deep_equal_container_name(type_anno)

    else:
        raise AssertionError(
            f"Unexpected type annotation to be compared deeply: {type_anno}. "
            f"The optionals nested in the containers should have been refused in "
            f"parse._translate._verify_symbol_table."
        )

    return Stripped(
        f"""\
!{callee}(
{I}{that_arg},
{I}{other_arg},
)"""
    )


def _generate_return_false_if(condition: Stripped) -> Stripped:
    """Generate the statement returning ``false`` if ``condition`` holds."""
    return Stripped(
        f"""\
if {condition} {{
{I}return false
}}"""
    )


@require(
    lambda type_anno: isinstance(type_anno, intermediate.ContainerTypeAnnotationAsTuple)
    and not _compares_by_equality_operator(type_anno)
)
def _generate_deep_equal_container(
    type_anno: intermediate.ContainerTypeAnnotation,
) -> Stripped:
    """Generate the function comparing deeply ``type_anno``."""
    value_type = golang_common.generate_type(
        type_anno, types_package=Identifier("ourtypes")
    )

    body: Stripped
    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        item_check = _generate_return_false_if(
            _generate_unequal_condition("that[i]", "other[i]", type_anno.items)
        )

        body = Stripped(
            f"""\
if len(that) != len(other) {{
{I}return false
}}

for i := range that {{
{I}{indent_but_first_line(item_check, I)}
}}

return true"""
        )

    elif isinstance(type_anno, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # A set holds only primitives and enumeration literals, which Go
        # compares with ``==`` as the keys of a map.
        body = Stripped(
            f"""\
if len(that) != len(other) {{
{I}return false
}}

for k := range that {{
{I}if _, ok := other[k]; !ok {{
{II}return false
{I}}}
}}

return true"""
        )

    elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
        item_checks = [
            _generate_return_false_if(
                _generate_unequal_condition(
                    f"that.Item{i + 1}", f"other.Item{i + 1}", item_type_anno
                )
            )
            for i, item_type_anno in enumerate(type_anno.items)
        ]

        item_checks_joined = "\n\n".join(item_checks)

        body = Stripped(
            f"""\
{item_checks_joined}

return true"""
        )

    else:
        assert_never(type_anno)

    return Stripped(
        f"""\
// Perform a comparison for deep equality between `that` and `other` container,
// recursing into its items.
func {_deep_equal_container_name(type_anno)}(
{I}that {value_type},
{I}other {value_type},
) bool {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_for_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate code for the deep equality function for ``cls``."""
    blocks: List[Stripped] = []

    for prop in cls.properties:
        that_var = golang_naming.variable_name(Identifier(f"that_{prop.name}"))
        other_var = golang_naming.variable_name(Identifier(f"other_{prop.name}"))

        getter_name = golang_naming.getter_name(prop.name)

        subblocks: List[Stripped] = [
            Stripped(
                f"""\
{that_var} := that.{getter_name}()
{other_var} := other.{getter_name}()"""
            )
        ]

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            subblocks.append(
                Stripped(
                    f"""\
if
{I}({that_var} == nil && {other_var} != nil) ||
{I}({that_var} != nil && {other_var} == nil) {{
{I}return false
}}"""
                )
            )

            if golang_pointering.is_pointer_type(prop.type_annotation):
                value_check = _generate_return_false_if(
                    _generate_unequal_condition(
                        f"*{that_var}", f"*{other_var}", type_anno
                    )
                )
            else:
                value_check = _generate_return_false_if(
                    _generate_unequal_condition(that_var, other_var, type_anno)
                )

            subblocks.append(
                Stripped(
                    f"""\
if {that_var} != nil {{
{I}{indent_but_first_line(value_check, I)}
}}"""
                )
            )
        else:
            subblocks.append(
                _generate_return_false_if(
                    _generate_unequal_condition(that_var, other_var, type_anno)
                )
            )

        blocks.append(Stripped("\n".join(subblocks)))

    blocks.append(Stripped("return true"))

    body = "\n\n".join(blocks)

    interface_name = golang_naming.interface_name(cls.name)

    function_name = golang_naming.private_function_name(
        Identifier(f"deep_equal_{cls.name}")
    )

    return Stripped(
        f"""\
// Perform a comparison for deep equality between `that` and `other` instance.
//
// The deep equality means that all the properties are checked for equality recursively.
func {function_name}(
{I}that ourtypes.{interface_name},
{I}other ourtypes.{interface_name},
) bool {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_dispatch_function(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the main ``DeepEqual`` function which then dispatches as necessary."""
    blocks = [
        Stripped(
            f"""\
if that.ModelType() != other.ModelType() {{
{I}return false
}}"""
        )
    ]

    cases: List[Stripped] = []
    for cls in symbol_table.concrete_classes:
        model_type_literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        deep_equal_func_name = golang_naming.private_function_name(
            Identifier(f"deep_equal_{cls.name}")
        )

        interface_name = golang_naming.interface_name(cls.name)

        cases.append(
            Stripped(
                f"""\
case ourtypes.{model_type_literal}:
{I}return {deep_equal_func_name}(
{II}that.(ourtypes.{interface_name}),
{II}other.(ourtypes.{interface_name}),
{I})"""
            )
        )

    cases_joined = "\n".join(cases)

    switch_stmt = Stripped(
        f"""\
switch that.ModelType() {{
{cases_joined}
}}"""
    )

    blocks.append(switch_stmt)

    blocks.append(
        Stripped(
            """\
panic(fmt.Sprintf("Unexpected model type: %d", that.ModelType()))"""
        )
    )

    body = "\n\n".join(blocks)

    return Stripped(
        f"""\
func DeepEqual(
{I}that ourtypes.IClass,
{I}other ourtypes.IClass,
) bool {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


#: Stand in for the import block, which is filled in at the very end: it
#: depends on what the generated code actually names, and an unused import does
#: not compile in Go.
_IMPORT_PLACEHOLDER = Stripped("")


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to perform a comparison of deep equality on instances."""
    blocks: List[Stripped] = [
        Stripped("package ourtesting"),
        golang_common.WARNING,
        _IMPORT_PLACEHOLDER,
    ]

    for cls in symbol_table.concrete_classes:
        blocks.append(_generate_for_cls(cls=cls))

    # NOTE (mristin):
    # We compare deeply the containers through functions of their own, one per
    # type moniker.
    observed_monikers: Set[str] = set()
    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            for (
                type_anno
            ) in intermediate.over_type_annotation_and_nested_type_annotations(
                prop.type_annotation
            ):
                if not isinstance(
                    type_anno, intermediate.ContainerTypeAnnotationAsTuple
                ) or _compares_by_equality_operator(type_anno):
                    continue

                moniker = golang_common.type_moniker(type_anno)
                if moniker in observed_monikers:
                    continue

                observed_monikers.add(moniker)

                blocks.append(_generate_deep_equal_container(type_anno=type_anno))

    blocks.append(_generate_dispatch_function(symbol_table=symbol_table))

    blocks.append(golang_common.WARNING)

    import_index = blocks.index(_IMPORT_PLACEHOLDER)

    import_lines: List[str] = []

    # NOTE (mristin):
    # ``reflect`` is named only by the comparison of a JSON-able value, which is
    # the one kind of property that Go can not compare structurally -- see
    # :py:func:`_generate_for_cls`.
    for module, literal in (
        ("bytes", f'{I}"bytes"'),
        ("fmt", f'{I}"fmt"'),
        ("reflect", f'{I}"reflect"'),
        (
            golang_common.COMMON_PACKAGE,
            f'{I}{golang_common.COMMON_PACKAGE} "{repo_url}/common"',
        ),
        ("ourtypes", f'{I}ourtypes "{repo_url}/types"'),
    ):
        if golang_common.names_package(blocks, module):
            import_lines.append(literal)

    blocks[import_index] = Stripped("import (\n" + "\n".join(import_lines) + "\n)")

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
