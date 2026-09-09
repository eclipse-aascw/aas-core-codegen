"""Generate code to perform a comparison of deep equality on instances."""

import io
from typing import List, Optional

from icontract import ensure

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


def _generate_for_cls(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate code for the deep equality function for ``cls``."""
    blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        that_var = golang_naming.variable_name(Identifier(f"that_{prop.name}"))
        other_var = golang_naming.variable_name(Identifier(f"other_{prop.name}"))

        getter_name = golang_naming.getter_name(prop.name)

        subblocks = [
            Stripped(
                f"""\
{that_var} := that.{getter_name}()
{other_var} := other.{getter_name}()"""
            )
        ]  # type: List[Stripped]

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

        cmp_subblock = None  # type: Optional[Stripped]

        type_anno = intermediate.beneath_optional(prop.type_annotation)

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and isinstance(
                type_anno.our_type,
                (intermediate.ConstrainedPrimitive, intermediate.Enumeration),
            )
        ):
            primitive_type = intermediate.try_primitive_type(type_anno)

            if golang_pointering.is_pointer_type(prop.type_annotation):
                cmp_subblock = Stripped(
                    f"""\
if *{that_var} != *{other_var} {{
{I}return false
}}"""
                )
            else:
                if primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                    cmp_subblock = Stripped(
                        f"""\
if !bytes.Equal(
{I}{that_var},
{I}{other_var},
) {{
{I}return false
}}"""
                    )
                else:
                    cmp_subblock = Stripped(
                        f"""\
if {that_var} != {other_var} {{
{I}return false
}}"""
                    )

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            if isinstance(type_anno.our_type, intermediate.Enumeration):
                raise AssertionError("Should have been handled before")

            elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                raise AssertionError("Should have been handled before")

            elif isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                cmp_subblock = Stripped(
                    f"""\
if !DeepEqual(
{I}{that_var},
{I}{other_var},
) {{
{I}return false
}}"""
                )

            else:
                # noinspection PyTypeChecker
                assert_never(type_anno.our_type)
        elif isinstance(type_anno, intermediate.ListTypeAnnotation):

            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We expect only lists of atomic values at the moment, "
                f"but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            # fmt: off
            direct_comparison_possible =  (
                isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation)
                or (
                    isinstance(type_anno.items, intermediate.OurTypeAnnotation)
                    and isinstance(
                        type_anno.items.our_type,
                        (
                            intermediate.Enumeration,
                            intermediate.ConstrainedPrimitive
                        )
                    )
                )
            )
            # fmt: on

            if direct_comparison_possible:
                items_primitive_type = intermediate.try_primitive_type(type_anno.items)

                if items_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                    cmp_subblock = Stripped(
                        f"""\
if 
{I}len({that_var}) !=
{I}len({other_var}) {{
{I}return false
}}
for i := range {that_var} {{
{I}if !bytes.Equal({that_var}[i], {other_var}[i]) {{
{II}return false
{I}}}
}}"""
                    )
                else:
                    cmp_subblock = Stripped(
                        f"""\
if 
{I}len({that_var}) !=
{I}len({other_var}) {{
{I}return false
}}
for i := range {that_var} {{
{I}if {that_var}[i] != {other_var}[i] {{
{II}return false
{I}}}
}}"""
                    )

            else:
                # fmt: off
                assert (
                    isinstance(type_anno.items, intermediate.OurTypeAnnotation)
                    and isinstance(
                        type_anno.items.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass)
                    )
                )
                # fmt: on

                cmp_subblock = Stripped(
                    f"""\
if 
{I}len({that_var}) !=
{I}len({other_var}) {{
{I}return false
}}
for i := range {that_var} {{
{I}if !DeepEqual(
{II}{that_var}[i],
{II}{other_var}[i],
{I}) {{
{II}return false
{I}}}
}}"""
                )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            item_cmp_blocks = []  # type: List[Stripped]

            for i, item_type_anno in enumerate(type_anno.items):
                item_that = f"{that_var}.Item{i + 1}"
                item_other = f"{other_var}.Item{i + 1}"

                if isinstance(
                    item_type_anno, intermediate.OurTypeAnnotation
                ) and isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    item_cmp_blocks.append(
                        Stripped(
                            f"""\
if !DeepEqual(
{I}{item_that},
{I}{item_other},
) {{
{I}return false
}}"""
                        )
                    )
                else:
                    if isinstance(
                        item_type_anno, intermediate.OurTypeAnnotation
                    ) and isinstance(item_type_anno.our_type, intermediate.Enumeration):
                        items_primitive_type = None
                    else:
                        items_primitive_type = intermediate.try_primitive_type(
                            item_type_anno
                        )
                        assert items_primitive_type is not None

                    if items_primitive_type is intermediate.PrimitiveType.BYTEARRAY:
                        item_cmp_blocks.append(
                            Stripped(
                                f"""\
if !bytes.Equal(
{I}{item_that},
{I}{item_other},
) {{
{I}return false
}}"""
                            )
                        )
                    else:
                        item_cmp_blocks.append(
                            Stripped(
                                f"""\
if {item_that} != {item_other} {{
{I}return false
}}"""
                            )
                        )

            cmp_subblock = Stripped("\n".join(item_cmp_blocks))

        assert cmp_subblock is not None

        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            cmp_subblock = Stripped(
                f"""\
if {that_var} != nil {{
{I}{indent_but_first_line(cmp_subblock, I)}
}}"""
            )

        subblocks.append(cmp_subblock)

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
{I}that aastypes.{interface_name},
{I}other aastypes.{interface_name},
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

    cases = []  # type: List[Stripped]
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
case aastypes.{model_type_literal}:
{I}return {deep_equal_func_name}(
{II}that.(aastypes.{interface_name}),
{II}other.(aastypes.{interface_name}),
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
{I}that aastypes.IClass,
{I}other aastypes.IClass,
) bool {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable, repo_url: Stripped) -> str:
    """Generate code to perform a comparison of deep equality on instances."""
    blocks = [
        Stripped("package aastesting"),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}"bytes"
{I}"fmt"
{I}aastypes "{repo_url}/types"
)"""
        ),
    ]  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        blocks.append(_generate_for_cls(cls=cls))

    blocks.append(_generate_dispatch_function(symbol_table=symbol_table))

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
