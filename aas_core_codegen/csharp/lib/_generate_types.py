"""Generate code of the data structures representing the meta-model."""
import io
import textwrap
from typing import (
    Optional,
    Dict,
    List,
    Tuple,
    cast,
    Union,
    Mapping,
    Final,
)

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen import specific_implementations
from aas_core_codegen.common import (
    Error,
    Identifier,
    assert_never,
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.csharp import (
    common as csharp_common,
    naming as csharp_naming,
    unrolling as csharp_unrolling,
    description as csharp_description,
)
from aas_core_codegen.csharp.common import (
    INDENT as I,
    INDENT2 as II,
)
from aas_core_codegen.intermediate import (
    construction as intermediate_construction,
)


# region Checks


def _human_readable_identifier(
    something: Union[
        intermediate.Enumeration, intermediate.AbstractClass, intermediate.ConcreteClass
    ]
) -> str:
    """
    Represent ``something`` in a human-readable text.

    The reader should be able to trace ``something`` back to the meta-model.
    """
    result: str

    if isinstance(something, intermediate.Enumeration):
        result = f"meta-model enumeration {something.name!r}"
    elif isinstance(something, intermediate.AbstractClass):
        result = f"meta-model abstract class {something.name!r}"
    elif isinstance(something, intermediate.ConcreteClass):
        result = f"meta-model concrete class {something.name!r}"
    else:
        assert_never(something)

    return result


def _verify_intra_structure_collisions(
    our_type: intermediate.OurType,
) -> Optional[Error]:
    """Verify that no member names collide in the C# structure of our type."""
    errors = []  # type: List[Error]

    if isinstance(our_type, intermediate.Enumeration):
        pass

    elif isinstance(our_type, intermediate.ConstrainedPrimitive):
        pass

    elif isinstance(our_type, intermediate.Class):
        observed_member_names = {}  # type: Dict[Identifier, str]

        for prop in our_type.properties:
            prop_name = csharp_naming.property_name(prop.name)
            if prop_name in observed_member_names:
                errors.append(
                    Error(
                        prop.parsed.node,
                        f"C# property {prop_name!r} corresponding "
                        f"to the meta-model property {prop.name!r} collides with "
                        f"the {observed_member_names[prop_name]}",
                    )
                )
            else:
                observed_member_names[prop_name] = (
                    f"C# property {prop_name!r} corresponding to "
                    f"the meta-model property {prop.name!r}"
                )

        observed_constructor_arg_names = {}  # type: Dict[Identifier, str]
        for constructor_arg in our_type.constructor.arguments:
            arg_name = csharp_naming.argument_name(constructor_arg.name)

            if arg_name in observed_constructor_arg_names:
                errors.append(
                    Error(
                        constructor_arg.parsed.node,
                        f"C# argument {arg_name!r} corresponding "
                        f"to the meta-model constructor argument {constructor_arg.name!r} "
                        f"collides with the {observed_constructor_arg_names[arg_name]}",
                    )
                )
            else:
                observed_constructor_arg_names[arg_name] = (
                    f"C# argument {arg_name!r} corresponding to "
                    f"the meta-model constructor argument {constructor_arg.name!r}"
                )

        for method in our_type.methods:
            method_name = csharp_naming.method_name(method.name)

            if method_name in observed_member_names:
                errors.append(
                    Error(
                        method.parsed.node,
                        f"C# method {method_name!r} corresponding "
                        f"to the meta-model method {method.name!r} collides with "
                        f"the {observed_member_names[method_name]}",
                    )
                )
            else:
                observed_member_names[method_name] = (
                    f"C# method {method_name!r} corresponding to "
                    f"the meta-model method {method.name!r}"
                )

            observed_method_arg_names = {}  # type: Dict[Identifier, str]
            for arg in method.arguments:
                arg_name = csharp_naming.argument_name(arg.name)

                if arg_name in observed_method_arg_names:
                    errors.append(
                        Error(
                            arg.parsed.node,
                            f"C# argument {arg_name!r} corresponding "
                            f"to the meta-model method argument {arg.name!r} "
                            f"of the method {method.name} "
                            f"collides with the {observed_method_arg_names[arg_name]}",
                        )
                    )
                else:
                    observed_method_arg_names[arg_name] = (
                        f"C# argument {arg_name!r} corresponding to "
                        f"the meta-model method argument {arg.name!r}"
                    )

    else:
        assert_never(our_type)

    if len(errors) > 0:
        return Error(
            our_type.parsed.node,
            f"Naming collision(s) in C# code for our type {our_type.name!r}",
            underlying=errors,
        )

    return None


def _verify_structure_name_collisions(
    symbol_table: intermediate.SymbolTable,
) -> List[Error]:
    """Verify that the C# names of the structures do not collide."""
    observed_structure_names: Dict[
        Identifier,
        Union[
            intermediate.Enumeration,
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
        ],
    ] = dict()

    errors = []  # type: List[Error]

    # region Inter-structure collisions

    for our_type in symbol_table.our_types:
        if not isinstance(
            our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            continue

        if isinstance(our_type, intermediate.Enumeration):
            name = csharp_naming.enum_name(our_type.name)
            other = observed_structure_names.get(name, None)

            if other is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The C# name {name!r} for the enumeration {our_type.name!r} "
                        f"collides with the same C# name "
                        f"coming from the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[name] = our_type

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            interface_name = csharp_naming.interface_name(our_type.name)

            other = observed_structure_names.get(interface_name, None)

            if other is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The C# name {interface_name!r} of the interface "
                        f"for the class {our_type.name!r} "
                        f"collides with the same C# name "
                        f"coming from the {_human_readable_identifier(other)}",
                    )
                )
            else:
                observed_structure_names[interface_name] = our_type

            if isinstance(our_type, intermediate.ConcreteClass):
                class_name = csharp_naming.class_name(our_type.name)

                other = observed_structure_names.get(class_name, None)

                if other is not None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The C# name {class_name!r} "
                            f"for the class {our_type.name!r} "
                            f"collides with the same C# name "
                            f"coming from the {_human_readable_identifier(other)}",
                        )
                    )
                else:
                    observed_structure_names[class_name] = our_type
        else:
            assert_never(our_type)

    # endregion

    # region Intra-structure collisions

    for our_type in symbol_table.our_types:
        collision_error = _verify_intra_structure_collisions(our_type=our_type)

        if collision_error is not None:
            errors.append(collision_error)

    # endregion

    return errors


class VerifiedIntermediateSymbolTable(intermediate.SymbolTable):
    """Represent a verified symbol table which can be used for code generation."""

    # noinspection PyInitNewSignature
    def __new__(
        cls, symbol_table: intermediate.SymbolTable
    ) -> "VerifiedIntermediateSymbolTable":
        raise AssertionError("Only for type annotation")


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def verify(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[VerifiedIntermediateSymbolTable], Optional[List[Error]]]:
    """Verify that C# code can be generated from the ``symbol_table``."""
    errors = []  # type: List[Error]

    structure_name_collisions = _verify_structure_name_collisions(
        symbol_table=symbol_table
    )

    errors.extend(structure_name_collisions)

    if len(errors) > 0:
        return None, errors

    return cast(VerifiedIntermediateSymbolTable, symbol_table), None


# endregion

# region Generation


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_enum(
    enum: intermediate.Enumeration,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate code for the enum."""
    writer = io.StringIO()

    if enum.description is not None:
        comment, comment_errors = csharp_description.generate_comment_for_our_type(
            enum.description
        )
        if comment_errors:
            return None, Error(
                enum.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    name = csharp_naming.enum_name(enum.name)
    if len(enum.literals) == 0:
        writer.write(f"public enum {name}\n{{\n}}")
        return Stripped(writer.getvalue()), None

    writer.write(f"public enum {name}\n{{\n")
    for i, literal in enumerate(enum.literals):
        if i > 0:
            writer.write(",\n\n")

        if literal.description:
            (
                literal_comment,
                literal_comment_errors,
            ) = csharp_description.generate_comment_for_enumeration_literal(
                literal.description
            )

            if literal_comment_errors:
                return None, Error(
                    literal.description.parsed.node,
                    f"Failed to generate the comment "
                    f"for the enumeration literal {literal.name!r}",
                    literal_comment_errors,
                )

            assert literal_comment is not None

            writer.write(textwrap.indent(literal_comment, I))
            writer.write("\n")

        writer.write(
            textwrap.indent(
                f"[EnumMember(Value = {csharp_common.string_literal(literal.value)})]\n"
                f"{csharp_naming.enum_literal_name(literal.name)}",
                I,
            )
        )

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_interface(
    cls: intermediate.ClassUnion,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate interface for the given class ``cls``."""
    writer = io.StringIO()

    if cls.description is not None:
        comment, comment_errors = csharp_description.generate_comment_for_our_type(
            cls.description
        )

        if comment_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                "Failed to generate the documentation comment",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    name = csharp_naming.interface_name(cls.name)

    inheritances = [inheritance.name for inheritance in cls.inheritances]
    if len(inheritances) == 0:
        # NOTE (mristin, 2022-05-05):
        # We need to include "IClass" only if there are no other parents.
        # Otherwise, one of the parents will already implement "IClass" so specifying
        # that this descendant implements "IClass" is redundant.
        inheritances = [Identifier("Class")]

    inheritance_names = list(map(csharp_naming.interface_name, inheritances))

    assert len(inheritances) > 0
    if len(inheritances) == 1:
        writer.write(f"public interface {name} : {inheritance_names[0]}\n{{\n")
    else:
        writer.write(f"public interface {name} :\n")
        for i, inheritance_name in enumerate(inheritance_names):
            if i > 0:
                writer.write(",\n")

            writer.write(textwrap.indent(inheritance_name, II))

        writer.write("\n{\n")

    # Code blocks separated by double newlines and indented once
    blocks = []  # type: List[Stripped]

    # region Getters and setters

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        prop_type = csharp_common.generate_type(type_annotation=prop.type_annotation)
        prop_name = csharp_naming.property_name(prop.name)

        if prop.description is not None:
            (
                prop_comment,
                prop_comment_errors,
            ) = csharp_description.generate_comment_for_property(prop.description)

            if prop_comment_errors is not None:
                return None, Error(
                    prop.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the property {prop.name!r}",
                    prop_comment_errors,
                )

            blocks.append(
                Stripped(
                    f"{prop_comment}\n"
                    f"public {prop_type} {prop_name} {{ get; set; }}"
                )
            )
        else:
            blocks.append(Stripped(f"public {prop_type} {prop_name} {{ get; set; }}"))

    # endregion

    # region Signatures

    for method in cls.methods:
        if method.specified_for is not cls:
            continue

        signature_blocks = []  # type: List[Stripped]

        if method.description is not None:
            (
                signature_comment,
                signature_comment_errors,
            ) = csharp_description.generate_comment_for_signature(method.description)

            if signature_comment_errors is not None:
                return None, Error(
                    method.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the method {method.name!r}",
                    signature_comment_errors,
                )

            assert signature_comment is not None

            signature_blocks.append(signature_comment)

        # fmt: off
        returns = (
            csharp_common.generate_type(type_annotation=method.returns)
            if method.returns is not None else "void"
        )
        # fmt: on

        arg_codes = []  # type: List[Stripped]
        for arg in method.arguments:
            arg_type = csharp_common.generate_type(type_annotation=arg.type_annotation)
            arg_name = csharp_naming.argument_name(arg.name)
            arg_codes.append(Stripped(f"{arg_type} {arg_name}"))

        signature_name = csharp_naming.method_name(method.name)
        if len(arg_codes) > 2:
            arg_block = ",\n".join(arg_codes)
            arg_block_indented = textwrap.indent(arg_block, I)
            signature_blocks.append(
                Stripped(f"public {returns} {signature_name}(\n{arg_block_indented});")
            )
        elif len(arg_codes) == 1:
            signature_blocks.append(
                Stripped(f"public {returns} {signature_name}({arg_codes[0]});")
            )
        else:
            assert len(arg_codes) == 0
            signature_blocks.append(Stripped(f"public {returns} {signature_name}();"))

        blocks.append(Stripped("\n".join(signature_blocks)))

    for prop in cls.properties:
        if prop.specified_for is not cls:
            continue

        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = csharp_naming.property_name(prop.name)
            items_type = csharp_common.generate_type(prop.type_annotation.value.items)
            blocks.append(
                Stripped(
                    f"""\
/// <summary>
/// Iterate over {prop_name}, if set, and otherwise return an empty enumerable.
/// </summary>
public IEnumerable<{items_type}> Over{prop_name}OrEmpty();"""
                )
            )

    # endregion

    if len(blocks) == 0:
        blocks = [Stripped("// Intentionally empty.")]

    for i, code in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(textwrap.indent(code, I))

    writer.write("\n}")

    return Stripped(writer.getvalue()), None


class _DescendBodyUnroller(csharp_unrolling.AbstractUnroller):
    """Generate the code that unrolls descent into an element."""

    #: If set, generates the code with unrolled yields.
    #: Otherwise, we do not unroll recursively.
    _recurse: Final[bool]

    #: Pre-computed descendability map. A type is descendable if we should unroll it
    #: further.
    _descendability: Final[Mapping[intermediate.TypeAnnotationUnion, bool]]

    def __init__(
        self,
        recurse: bool,
        descendability: Mapping[intermediate.TypeAnnotationUnion, bool],
    ) -> None:
        """Initialize with the given values."""
        self._recurse = recurse
        self._descendability = descendability

    def _unroll_primitive_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.PrimitiveTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[csharp_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        # We can not descend into a primitive type.
        return []

    def _unroll_our_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OurTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[csharp_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            return []

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # We can not descend into a primitive type.
            return []

        assert isinstance(our_type, intermediate.Class)  # Exhaustively match

        result = [csharp_unrolling.Node(f"yield return {unrollee_expr};", children=[])]

        if self._recurse:
            if self._descendability[type_annotation]:
                recurse_var = csharp_unrolling.AbstractUnroller._loop_var_name(
                    level=item_level, suffix="Item"
                )

                result.append(
                    csharp_unrolling.Node(
                        text=textwrap.dedent(
                            f"""\
                        // Recurse
                        foreach (var {recurse_var} in {unrollee_expr}.Descend())
                        {{
                            yield return {recurse_var};
                        }}"""
                        ),
                        children=[],
                    )
                )
            else:
                result.append(
                    csharp_unrolling.Node(
                        text="// Recursive descent ends here.", children=[]
                    )
                )

        return result

    def _unroll_list_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.ListTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[csharp_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        item_var = csharp_unrolling.AbstractUnroller._loop_var_name(
            level=item_level, suffix="Item"
        )

        children = self.unroll(
            unrollee_expr=item_var,
            type_annotation=type_annotation.items,
            path=[],  # Path is unused in this context
            item_level=item_level + 1,
            key_value_level=key_value_level,
        )

        if len(children) == 0:
            return []

        node = csharp_unrolling.Node(
            text=f"foreach (var {item_var} in {unrollee_expr})",
            children=children,
        )

        return [node]

    def _unroll_tuple_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.TupleTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[csharp_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        nodes = []  # type: List[csharp_unrolling.Node]

        for i, item_type_annotation in enumerate(type_annotation.items):
            item_expr = f"{unrollee_expr}.Item{i + 1}"

            nodes.extend(
                self.unroll(
                    unrollee_expr=item_expr,
                    type_annotation=item_type_annotation,
                    path=[],  # Path is unused in this context
                    item_level=item_level,
                    key_value_level=key_value_level,
                )
            )

        return nodes

    def _unroll_optional_type_annotation(
        self,
        unrollee_expr: str,
        type_annotation: intermediate.OptionalTypeAnnotation,
        path: List[str],
        item_level: int,
        key_value_level: int,
    ) -> List[csharp_unrolling.Node]:
        """Generate code for the given specific ``type_annotation``."""
        children = self.unroll(
            unrollee_expr=unrollee_expr,
            type_annotation=type_annotation.value,
            path=path,
            item_level=item_level,
            key_value_level=key_value_level,
        )

        if len(children) == 0:
            return []

        return [
            csharp_unrolling.Node(
                text=f"if ({unrollee_expr} != null)", children=children
            )
        ]


def _generate_descend_body(cls: intermediate.ConcreteClass, recurse: bool) -> Stripped:
    """
    Generate the body of the ``Descend`` and ``DescendOnce`` methods.

    With this function, we can unroll the recursion as a simple optimization
    in the recursive case.
    """
    blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        descendability = intermediate.map_descendability(
            type_annotation=prop.type_annotation
        )

        if not descendability[prop.type_annotation]:
            continue

        # region Unroll

        unroller = _DescendBodyUnroller(recurse=recurse, descendability=descendability)

        roots = unroller.unroll(
            unrollee_expr=csharp_naming.property_name(prop.name),
            type_annotation=prop.type_annotation,
            path=[],  # We do not use path in this context
            item_level=0,
            key_value_level=0,
        )

        assert len(roots) > 0, (
            "Since the type annotation was descendable, we must have obtained "
            "at least one unrolling node"
        )

        blocks.extend(Stripped(csharp_unrolling.render(root)) for root in roots)

        # endregion

    if len(blocks) == 0:
        blocks.append(Stripped("// No descendable properties\nyield break;"))

    return Stripped("\n\n".join(blocks))


def _generate_descend_once_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the ``DescendOnce`` method for the concrete class ``cls``."""

    body = _generate_descend_body(cls=cls, recurse=False)

    indented_body = textwrap.indent(body, I)

    return Stripped(
        f"""\
/// <summary>
/// Iterate over all the class instances referenced from this instance
/// without further recursion.
/// </summary>
public IEnumerable<IClass> DescendOnce()
{{
{indented_body}
}}"""
    )


def _generate_descend_method(cls: intermediate.ConcreteClass) -> Stripped:
    """Generate the recursive ``Descend`` method for the concrete class ``cls``."""

    body = _generate_descend_body(cls=cls, recurse=True)

    indented_body = textwrap.indent(body, I)

    return Stripped(
        f"""\
/// <summary>
/// Iterate recursively over all the class instances referenced from this instance.
/// </summary>
public IEnumerable<IClass> Descend()
{{
{indented_body}
}}"""
    )


def _generate_default_value(default: intermediate.Default) -> Stripped:
    """Generate code representing the default value of an argument."""
    code = None  # type: Optional[str]

    if default is not None:
        if isinstance(default, intermediate.DefaultPrimitive):
            if default.value is None:
                code = "null"
            elif isinstance(default.value, bool):
                code = "true" if default.value else "false"
            elif isinstance(default.value, str):
                code = csharp_common.string_literal(default.value)
            elif isinstance(default.value, int):
                code = str(default.value)
            elif isinstance(default.value, float):
                code = f"{default}d"
            else:
                assert_never(default.value)
        elif isinstance(default, intermediate.DefaultEnumerationLiteral):
            code = ".".join(
                [
                    csharp_naming.enum_name(default.enumeration.name),
                    csharp_naming.enum_literal_name(default.literal.name),
                ]
            )
        else:
            assert_never(default)

    assert code is not None
    return Stripped(code)


@require(lambda cls: not cls.is_implementation_specific)
@require(lambda cls: not cls.constructor.is_implementation_specific)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_constructor(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the constructor function for the given concrete class ``cls``.

    Return empty string if there is an empty constructor.
    """
    if (
        len(cls.constructor.arguments) == 0
        and len(cls.constructor.inlined_statements) == 0
    ):
        return Stripped(""), None

    cls_name = csharp_naming.class_name(cls.name)

    blocks = []  # type: List[str]

    arg_codes = []  # type: List[str]
    for arg in cls.constructor.arguments:
        arg_type = csharp_common.generate_type(type_annotation=arg.type_annotation)
        arg_name = csharp_naming.argument_name(arg.name)

        if arg.default is None:
            arg_codes.append(Stripped(f"{arg_type} {arg_name}"))
        else:
            arg_codes.append(
                Stripped(
                    f"{arg_type} {arg_name} = {_generate_default_value(arg.default)}"
                )
            )

    if len(arg_codes) == 0:
        blocks.append(f"public {cls_name}()\n{{")
    if len(arg_codes) == 1:
        blocks.append(f"public {cls_name}({arg_codes[0]})\n{{")
    else:
        arg_block = ",\n".join(arg_codes)
        arg_block_indented = textwrap.indent(arg_block, I)
        blocks.append(Stripped(f"public {cls_name}(\n{arg_block_indented})\n{{"))

    body = []  # type: List[str]
    for stmt in cls.constructor.inlined_statements:
        if isinstance(stmt, intermediate_construction.AssignArgument):
            if stmt.default is None:
                body.append(
                    f"{csharp_naming.property_name(stmt.name)} = "
                    f"{csharp_naming.argument_name(stmt.argument)};"
                )
            else:
                if isinstance(stmt.default, intermediate_construction.EmptyList):
                    prop = cls.properties_by_name[stmt.name]

                    type_anno = prop.type_annotation
                    while isinstance(type_anno, intermediate.OptionalTypeAnnotation):
                        type_anno = type_anno.value

                    prop_type = csharp_common.generate_type(type_annotation=type_anno)

                    arg_name = csharp_naming.argument_name(stmt.argument)

                    # Write the assignment as a ternary operator
                    writer = io.StringIO()
                    writer.write(f"{csharp_naming.property_name(stmt.name)} = ")
                    writer.write(f"({arg_name} != null)\n")
                    writer.write(textwrap.indent(f"? {arg_name}\n", I))
                    writer.write(textwrap.indent(f": new {prop_type}();", I))

                    body.append(writer.getvalue())
                elif isinstance(
                    stmt.default, intermediate_construction.DefaultEnumLiteral
                ):
                    literal_code = ".".join(
                        [
                            csharp_naming.enum_name(stmt.default.enum.name),
                            csharp_naming.enum_literal_name(stmt.default.literal.name),
                        ]
                    )

                    arg_name = csharp_naming.argument_name(stmt.argument)

                    body.append(
                        Stripped(
                            f"""\
{csharp_naming.property_name(stmt.name)} = {arg_name} ?? {literal_code};"""
                        )
                    )
                else:
                    assert_never(stmt.default)

        else:
            assert_never(stmt)

    blocks.append("\n".join(textwrap.indent(stmt_code, I) for stmt_code in body))

    blocks.append("}")

    return Stripped("\n".join(blocks)), None


@require(lambda cls: not cls.is_implementation_specific)
@ensure(lambda result: (result[0] is None) ^ (result[1] is None))
def _generate_class(
    cls: intermediate.ConcreteClass,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate code for the given concrete class ``cls``."""
    # Code blocks to be later joined by double newlines and indented once
    blocks = []  # type: List[Stripped]

    # region Getters and setters

    for prop in cls.properties:
        prop_type = csharp_common.generate_type(type_annotation=prop.type_annotation)

        prop_name = csharp_naming.property_name(prop.name)

        prop_blocks = []  # type: List[Stripped]

        if prop.description is not None:
            (
                prop_comment,
                prop_comment_errors,
            ) = csharp_description.generate_comment_for_property(prop.description)
            if prop_comment_errors:
                return None, Error(
                    prop.description.parsed.node,
                    f"Failed to generate the documentation comment "
                    f"for the property {prop.name!r}",
                    prop_comment_errors,
                )

            assert prop_comment is not None

            prop_blocks.append(prop_comment)

        prop_blocks.append(Stripped(f"public {prop_type} {prop_name} {{ get; set; }}"))

        blocks.append(Stripped("\n".join(prop_blocks)))

    # endregion

    # region OverXOrEmpty getter

    for prop in cls.properties:
        if isinstance(
            prop.type_annotation, intermediate.OptionalTypeAnnotation
        ) and isinstance(prop.type_annotation.value, intermediate.ListTypeAnnotation):
            prop_name = csharp_naming.property_name(prop.name)
            items_type = csharp_common.generate_type(prop.type_annotation.value.items)

            blocks.append(
                Stripped(
                    f"""\
/// <summary>
/// Iterate over {prop_name}, if set, and otherwise return an empty enumerable.
/// </summary>
public IEnumerable<{items_type}> Over{prop_name}OrEmpty()
{{
{I}return {prop_name}
{II}?? System.Linq.Enumerable.Empty<{items_type}>();
}}"""
                )
            )

    # endregion

    # region Methods

    errors = []  # type: List[Error]

    for method in cls.methods:
        if isinstance(method, intermediate.ImplementationSpecificMethod):
            # NOTE (mristin, 2022-05-18):
            # We have to repeat the implementation of the method in all the descendants
            # since we share only interfaces between the classes, but not
            # the implementations.
            #
            # This makes the code a bit larger, but the class hierarchy is much simpler
            # and the individual classes are much easier to grasp.
            implementation_key = specific_implementations.ImplementationKey(
                f"Types/{method.specified_for.name}/{method.name}.cs"
            )

            implementation = spec_impls.get(implementation_key, None)

            if implementation is None:
                errors.append(
                    Error(
                        method.parsed.node,
                        f"The implementation is missing for "
                        f"the implementation-specific method: {implementation_key}",
                    )
                )
                continue

            blocks.append(implementation)
        else:
            # NOTE (mristin, 2021-09-16):
            # At the moment, we do not transpile the method body and its contracts.
            # We want to finish the meta-model for the V3 and fix de/serialization
            # before taking on this rather hard task.

            errors.append(
                Error(
                    cls.parsed.node,
                    "At the moment, we do not transpile the method body and "
                    "its contracts. We want to finish the meta-model for the V3 and "
                    "fix de/serialization before taking on this rather hard task.",
                )
            )

    blocks.append(_generate_descend_once_method(cls=cls))

    blocks.append(_generate_descend_method(cls=cls))

    visit_name = csharp_naming.method_name(Identifier(f"visit_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Accept the <paramref name="visitor" /> to visit this instance
/// for double dispatch.
/// </summary>
public void Accept(Visitation.IVisitor visitor)
{{
{I}visitor.{visit_name}(this);
}}"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Accept the visitor to visit this instance for double dispatch
/// with the <paramref name="context" />.
/// </summary>
public void Accept<TContext>(
{I}Visitation.IVisitorWithContext<TContext> visitor,
{I}TContext context)
{{
{I}visitor.{visit_name}(this, context);
}}"""
        )
    )

    transform_name = csharp_naming.method_name(Identifier(f"transform_{cls.name}"))

    blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Accept the <paramref name="transformer" /> to transform this instance
/// for double dispatch.
/// </summary>
public T Transform<T>(Visitation.ITransformer<T> transformer)
{{
{I}return transformer.{transform_name}(this);
}}"""
        )
    )

    blocks.append(
        Stripped(
            f"""\
/// <summary>
/// Accept the <paramref name="transformer" /> to visit this instance
/// for double dispatch with the <paramref name="context" />.
/// </summary>
public T Transform<TContext, T>(
{I}Visitation.ITransformerWithContext<TContext, T> transformer,
{I}TContext context)
{{
{I}return transformer.{transform_name}(this, context);
}}"""
        )
    )

    # endregion

    # region Constructor

    if cls.constructor.is_implementation_specific:
        implementation_key = specific_implementations.ImplementationKey(
            f"Types/{cls.name}/{cls.name}.cs"
        )
        implementation = spec_impls.get(implementation_key, None)

        if implementation is None:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"The implementation of the implementation-specific constructor "
                    f"is missing: {implementation_key}",
                )
            )
        else:
            blocks.append(implementation)
    else:
        constructor_block, error = _generate_constructor(cls=cls)

        if error is not None:
            errors.append(error)
        else:
            # NOTE (mristin, 2022-06-21):
            # Empty constructor will be automatically generated by the compiler.
            if constructor_block != "":
                assert constructor_block is not None
                blocks.append(constructor_block)

    # endregion

    if len(errors) > 0:
        return None, Error(
            cls.parsed.node,
            f"Failed to generate the code for the class {cls.name}",
            errors,
        )

    # NOTE (mristin, 2023-02-08):
    # Since C# does not support multiple inheritance, we model all the abstract classes
    # as interfaces. Hence, a class only implements interfaces and does not extend
    # any abstract class.
    #
    # Moreover, we generate an interface for *each* concrete class. This is necessary
    # for two reasons. First, if a concrete class has descendants, we have to allow
    # for polymorphism and multiple inheritance from multiple concrete classes (which
    # is allowed in the meta-model). Second, we want to allow the downstream users to
    # introduce custom enhancements and wrap our data structures. To that end, we
    # generate an interface for each concrete class, even if it has no descendants.
    # This allows the downstream users to still use our interfaces, but provide
    # custom extensions.
    #
    # Finally, every class of the meta-model also implements the general
    # ``IClass`` interface.

    interface_name = csharp_naming.interface_name(cls.name)

    name = csharp_naming.class_name(cls.name)

    writer = io.StringIO()

    if cls.description is not None:
        comment, comment_errors = csharp_description.generate_comment_for_our_type(
            cls.description
        )
        if comment_errors is not None:
            return None, Error(
                cls.description.parsed.node,
                "Failed to generate the comment description",
                comment_errors,
            )

        assert comment is not None

        writer.write(comment)
        writer.write("\n")

    writer.write(f"public class {name} : {interface_name}\n{{\n")

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
    symbol_table: VerifiedIntermediateSymbolTable,
    namespace: csharp_common.NamespaceIdentifier,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """
    Generate code of the data structures representing the meta-model.

    The ``namespace`` defines the AAS C# namespace.
    """
    code_blocks = [
        Stripped(
            f"""\
/// <summary>
/// Represent a general class of an AAS model.
/// </summary>
public interface IClass
{{
{I}/// <summary>
{I}/// Iterate over all the class instances referenced from this instance
{I}/// without further recursion.
{I}/// </summary>
{I}public IEnumerable<IClass> DescendOnce();

{I}/// <summary>
{I}/// Iterate recursively over all the class instances referenced from this instance.
{I}/// </summary>
{I}public IEnumerable<IClass> Descend();

{I}/// <summary>
{I}/// Accept the <paramref name="visitor" /> to visit this instance
{I}/// for double dispatch.
{I}/// </summary>
{I}public void Accept(Visitation.IVisitor visitor);

{I}/// <summary>
{I}/// Accept the visitor to visit this instance for double dispatch
{I}/// with the <paramref name="context" />.
{I}/// </summary>
{I}public void Accept<TContext>(
{II}Visitation.IVisitorWithContext<TContext> visitor,
{II}TContext context);

{I}/// <summary>
{I}/// Accept the <paramref name="transformer" /> to transform this instance
{I}/// for double dispatch.
{I}/// </summary>
{I}public T Transform<T>(Visitation.ITransformer<T> transformer);

{I}/// <summary>
{I}/// Accept the <paramref name="transformer" /> to visit this instance
{I}/// for double dispatch with the <paramref name="context" />.
{I}/// </summary>
{I}public T Transform<TContext, T>(
{II}Visitation.ITransformerWithContext<TContext, T> transformer,
{II}TContext context);
}}"""
        )
    ]  # type: List[Stripped]

    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types:
        if not isinstance(
            our_type,
            (
                intermediate.Enumeration,
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
            ),
        ):
            continue

        if (
            isinstance(our_type, intermediate.Class)
            and our_type.is_implementation_specific
        ):
            implementation_key = specific_implementations.ImplementationKey(
                f"Types/{our_type.name}.cs"
            )

            code = spec_impls.get(implementation_key, None)
            if code is None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"The implementation is missing "
                        f"for the implementation-specific class: {implementation_key}",
                    )
                )
                continue

            code_blocks.append(code)
            continue

        if isinstance(our_type, intermediate.Enumeration):
            code, error = _generate_enum(enum=our_type)
            if error is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"Failed to generate the code for "
                        f"the enumeration {our_type.name!r}",
                        [error],
                    )
                )
                continue

            assert code is not None
            code_blocks.append(code)

        elif isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            code, error = _generate_interface(cls=our_type)
            if error is not None:
                errors.append(
                    Error(
                        our_type.parsed.node,
                        f"Failed to generate the interface code for "
                        f"the class {our_type.name!r}",
                        [error],
                    )
                )
                continue

            assert code is not None
            code_blocks.append(code)

            if isinstance(our_type, intermediate.ConcreteClass):
                code, error = _generate_class(cls=our_type, spec_impls=spec_impls)
                if error is not None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"Failed to generate the code for "
                            f"the concrete class {our_type.name!r}",
                            [error],
                        )
                    )
                    continue

                assert code is not None
                code_blocks.append(code)

        else:
            assert_never(our_type)

    if len(errors) > 0:
        return None, errors

    using_directives = []  # type: List[Stripped]
    using_directives.extend(
        csharp_common.generate_using_aas_directive_if_necessary(namespace)
    )

    using_directives.append(
        Stripped(
            """\
using EnumMemberAttribute = System.Runtime.Serialization.EnumMemberAttribute;

using System.Collections.Generic;  // can't alias"""
        )
    )

    code_blocks_joined = "\n\n".join(code_blocks)

    blocks = [
        csharp_common.WARNING,
        Stripped("\n".join(using_directives)),
        Stripped(
            f"""\
namespace {namespace}
{{
{I}{indent_but_first_line(code_blocks_joined, I)}
}}  // namespace {namespace}"""
        ),
        csharp_common.WARNING,
    ]  # type: List[Stripped]

    out = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            out.write("\n\n")

        out.write(block)

    out.write("\n")

    return out.getvalue(), None


# endregion

assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
