"""Generate code of verification logic."""
import io
import re
from typing import (
    AbstractSet,
    Optional,
    List,
    Tuple,
    Union,
    Sequence,
    Mapping,
    Set,
    Final,
    Dict,
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
    wrap_text_into_lines,
)
from aas_core_codegen.cpp import (
    aliasing as cpp_aliasing,
    common as cpp_common,
    naming as cpp_naming,
    description as cpp_description,
    transpilation as cpp_transpilation,
    optionaling as cpp_optionaling,
    over as cpp_over,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
)
from aas_core_codegen.intermediate import type_inference as intermediate_type_inference
from aas_core_codegen.intermediate import uses as intermediate_uses
from aas_core_codegen.parse import tree as parse_tree


def _generate_return_type(verification: intermediate.Verification) -> Stripped:
    """Generate the C++ return type of the ``verification`` function."""
    if verification.returns is None:
        return Stripped("void")

    return cpp_common.generate_type(
        type_annotation=verification.returns,
        types_namespace=cpp_common.TYPES_NAMESPACE,
    )


def _type_parameter_name(argument: intermediate.Argument) -> Identifier:
    """
    Generate the name of the template parameter for the items of the ``argument``.

    For example, ``items`` gives ``ItemsT``.
    """
    return Identifier(f"{cpp_naming.class_name(argument.name)}T")


def _is_generic(verification: intermediate.VerificationUnion) -> bool:
    """
    Check whether the transpiled ``verification`` function is a template.

    The verification function is a template if it has one or more generic
    sequences, see :py:func:`intermediate.generic_sequence_item_class`.
    The implementation-specific verification functions declare their templates
    in their snippets.
    """
    return isinstance(verification, intermediate.TranspilableVerification) and any(
        intermediate.generic_sequence_item_class(arg) is not None
        for arg in verification.arguments
    )


def _generate_signature(
    verification: Union[
        intermediate.TranspilableVerification,
        intermediate.PatternVerification,
    ],
) -> Stripped:
    """
    Generate the signature of the ``verification`` function.

    The ``std::vector`` is invariant in C++, so we declare a template parameter
    for the items of each generic sequence, see
    :py:func:`intermediate.generic_sequence_item_class`. This way, the vectors of
    the descendants can be passed without a copy. The virtual methods can not be
    templates in C++, so only the verification functions have generic sequences.

    The template parameters are constrained by ``static_assert``'s in the body
    instead of ``std::enable_if`` in the signature so that the template can be
    declared and defined separately.
    """
    type_parameters: List[Identifier] = []
    arg_definitions: List[Stripped] = []
    for arg in verification.arguments:
        arg_name = cpp_naming.argument_name(arg.name)

        if intermediate.generic_sequence_item_class(arg) is None:
            arg_type = cpp_common.generate_argument_type(
                argument=arg, types_namespace=cpp_common.TYPES_NAMESPACE
            )
        else:
            type_parameter = _type_parameter_name(arg)
            type_parameters.append(type_parameter)

            vector_type = Stripped(
                f"""\
std::vector<
{I}std::shared_ptr<{type_parameter}>
>"""
            )
            if isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
                arg_type = Stripped(
                    f"""\
const common::optional<
{I}{indent_but_first_line(vector_type, I)}
>&"""
                )
            else:
                arg_type = Stripped(f"const {vector_type}&")

        arg_definitions.append(Stripped(f"{arg_type} {arg_name}"))

    function_name = cpp_naming.function_name(verification.name)
    return_type = _generate_return_type(verification)

    if len(arg_definitions) == 0:
        signature = Stripped(f"{return_type} {function_name}()")
    else:
        arg_definitions_joined = ",\n".join(arg_definitions)
        signature = Stripped(
            f"""\
{return_type} {function_name}(
{I}{indent_but_first_line(arg_definitions_joined, I)}
)"""
        )

    if len(type_parameters) == 0:
        return signature

    type_parameters_joined = ",\n".join(
        f"typename {type_parameter}" for type_parameter in type_parameters
    )
    return Stripped(
        f"""\
template<
{I}{indent_but_first_line(type_parameters_joined, I)}
>
{signature}"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_verification_function_definition(
    verification: Union[
        intermediate.ImplementationSpecificVerification,
        intermediate.TranspilableVerification,
        intermediate.PatternVerification,
    ],
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Generate the definition of a verification functions."""
    if isinstance(verification, intermediate.ImplementationSpecificVerification):
        implementation_key = specific_implementations.ImplementationKey(
            f"verification/{verification.name}.hpp"
        )

        code = spec_impls.get(implementation_key, None)

        if code is None:
            return None, Error(
                verification.parsed.node,
                f"The header snippet is missing for "
                f"the implementation-specific verification "
                f"function: {implementation_key}",
            )

        return code, None

    remarks_on_generic_sequences: List[str] = []
    for arg in verification.arguments:
        item_cls = intermediate.generic_sequence_item_class(arg)
        if item_cls is None:
            continue

        interface_name = (
            f"{cpp_common.TYPES_NAMESPACE}::{cpp_naming.interface_name(item_cls.name)}"
        )
        remarks_on_generic_sequences.append(
            f"\\tparam {_type_parameter_name(arg)} type of the items of "
            f"\\p {cpp_naming.argument_name(arg.name)}, {interface_name} or one of "
            f"its descendants, so that the vectors of the descendants can be passed "
            f"without a copy, as std::vector is invariant"
        )

    blocks: List[Stripped] = []
    if verification.description is not None:
        comment, errors = cpp_description.generate_comment_for_summary_remarks(
            description=verification.description,
            context=cpp_description.Context(
                namespace=cpp_common.VERIFICATION_NAMESPACE, cls_or_enum=None
            ),
            extra_remarks=remarks_on_generic_sequences,
        )
        if errors is not None:
            return None, Error(
                verification.parsed.node,
                f"Failed to generate the description for "
                f"verification function {verification.name!r}",
                errors,
            )
        assert comment is not None
        blocks.append(comment)
    elif len(remarks_on_generic_sequences) > 0:
        blocks.append(
            cpp_description.documentation_comment(
                Stripped("\n\n".join(remarks_on_generic_sequences))
            )
        )
    else:
        pass

    blocks.append(Stripped(f"{_generate_signature(verification)};"))

    return Stripped("\n".join(blocks)), None


def _generate_definition_of_verify_constrained_primitive(
    constrained_primitive: intermediate.ConstrainedPrimitive,
) -> Stripped:
    """Generate the def. of a verification function for the constrained primitive."""
    verify_name = cpp_naming.function_name(
        Identifier(f"verify_{constrained_primitive.name}")
    )

    arg_type = cpp_common.generate_primitive_type_with_const_ref_if_applicable(
        constrained_primitive.constrainee
    )

    arg_name = cpp_naming.argument_name(Identifier("that"))

    if cpp_common.primitive_type_is_referencable(constrained_primitive.constrainee):
        documentation_comment = Stripped(
            """\
/**
 * \\brief Verify that the invariants hold for \\p that value.
 *
 * The \\p that value should outlive the verification.
 *
 * \\param that value to be verified
 * \\return Iterable over constraint violations
 */"""
        )
    else:
        documentation_comment = Stripped(
            """\
/**
 * \\brief Verify that the invariants hold for \\p that value.
 *
 * \\param that value to be verified
 * \\return Iterable over constraint violations
 */"""
        )

    return Stripped(
        f"""\
{documentation_comment}
std::unique_ptr<IVerification> {verify_name}(
{I}{arg_type} {arg_name}
);"""
    )


def _check_no_calls_to_internal_verifications(
    verification: intermediate.TranspilableVerification,
    symbol_table: intermediate.SymbolTable,
) -> List[Error]:
    """
    Check that the public generic ``verification`` calls no internal verification.

    The public generic verification functions are templates defined in the header,
    see :py:func:`_is_generic`, while the internal verification functions are
    declared only in the implementation file.
    """
    errors: List[Error] = []
    for node_in_body in verification.parsed.body:
        for node in parse_tree.over_nodes(node_in_body):
            if not isinstance(node, parse_tree.FunctionCall):
                continue

            callee = symbol_table.verification_functions_by_name.get(
                node.name.identifier, None
            )
            if (
                callee is None
                or callee.visibility is not intermediate.Visibility.INTERNAL
            ):
                continue

            errors.append(
                Error(
                    node.original_node,
                    f"The public verification function {verification.name!r} has "
                    f"generic sequences, so we generate it in C++ as a template "
                    f"defined in the header. However, it calls the internal "
                    f"verification function {callee.name!r}, which is declared "
                    f"only in the implementation file. Please make "
                    f"{callee.name!r} public, or {verification.name!r} internal.",
                )
            )

    return errors


class _TranspilableVerificationTranspiler(cpp_transpilation.Transpiler):
    """Transpile the body of a :class:`TranspilableVerification`."""

    # fmt: off
    @require(
        lambda environment, verification:
        all(
            environment.find(arg.name) is not None
            for arg in verification.arguments
        ),
        "All arguments defined in the environment"
    )
    # fmt: on
    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        is_optional_map: Mapping[parse_tree.Node, bool],
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        is_optional_before_downcast_map: Mapping[parse_tree.Node, bool],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
        verification: intermediate.TranspilableVerification,
        aliasing: cpp_aliasing.Aliasing,
    ) -> None:
        """Initialize with the given values."""
        cpp_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            is_optional_map=is_optional_map,
            downcast_map=downcast_map,
            is_optional_before_downcast_map=is_optional_before_downcast_map,
            environment=environment,
            types_namespace=cpp_common.TYPES_NAMESPACE,
            aliasing=aliasing,
        )

        self._symbol_table = symbol_table

        self._argument_name_set = frozenset(arg.name for arg in verification.arguments)

        # NOTE (mristin):
        # The type inference propagates the very type annotation of the items of
        # an argument to the loop variables, the generator variables and
        # the indexed items, so we can tell by the identity of the type annotation
        # that a value is of the template parameter of a generic sequence.
        type_parameter_by_items_id: Dict[int, Identifier] = dict()
        for arg in verification.arguments:
            if intermediate.generic_sequence_item_class(arg) is None:
                continue

            arg_type_anno = environment.find(arg.name)
            assert arg_type_anno is not None

            list_type_anno = intermediate_type_inference.beneath_optional(arg_type_anno)
            assert isinstance(
                list_type_anno, intermediate_type_inference.ListTypeAnnotation
            )

            type_parameter_by_items_id[id(list_type_anno.items)] = _type_parameter_name(
                arg
            )

        self._type_parameter_by_items_id = type_parameter_by_items_id

    def _type_parameter_of(
        self, type_annotation: intermediate_type_inference.TypeAnnotationUnion
    ) -> Optional[Identifier]:
        return self._type_parameter_by_items_id.get(id(type_annotation), None)

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(cpp_naming.variable_name(node.identifier)), None

        if node.identifier in self._argument_name_set:
            return Stripped(cpp_naming.argument_name(node.identifier)), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant = cpp_naming.constant_name(node.identifier)
            return Stripped(f"{cpp_common.CONSTANTS_NAMESPACE}::{constant}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            return Stripped(cpp_naming.function_name(node.identifier)), None

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(
                    f"{cpp_common.TYPES_NAMESPACE}::{cpp_naming.enum_name(node.identifier)}"
                ),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to C++. We could not find it neither in the constants, nor in "
            f"verification functions, nor as an enumeration. "
            f"If you expect this name to be transpilable, please contact "
            f"the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_implementation_of_transpilable_verification(
    verification: intermediate.TranspilableVerification,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Transpile the verification to a function implementation."""
    inference = type_inference.by_verification[verification]

    aliasing, aliasing_errors = cpp_aliasing.analyze(
        body=verification.parsed.body,
        arguments=verification.arguments,
        type_map=inference.type_map,
        binds_self=False,
    )
    if aliasing_errors is not None:
        return None, Error(
            verification.parsed.node,
            f"Failed to transpile the verification function {verification.name!r} "
            f"so that its C++ variables alias the values as in Python",
            aliasing_errors,
        )

    assert aliasing is not None

    optional_inferrer = cpp_optionaling.Inferrer(
        environment=inference.environment_with_args,
        type_map=inference.type_map,
        downcast_map=inference.downcast_map,
    )
    for node in verification.parsed.body:
        _ = optional_inferrer.transform(node)

    if len(optional_inferrer.errors) > 0:
        return None, Error(
            verification.parsed.node,
            f"Failed to infer whether one or more nodes are ``common::optional`` "
            f"in the verification function {verification.name!r}",
            optional_inferrer.errors,
        )

    transpiler = _TranspilableVerificationTranspiler(
        type_map=inference.type_map,
        is_optional_map=optional_inferrer.is_optional_map,
        downcast_map=inference.downcast_map,
        is_optional_before_downcast_map=(
            optional_inferrer.is_optional_before_downcast_map
        ),
        environment=inference.environment_with_args,
        symbol_table=symbol_table,
        verification=verification,
        aliasing=aliasing,
    )

    body: List[Stripped] = []
    for node in verification.parsed.body:
        stmt, error = transpiler.transform(node)
        if error is not None:
            return None, Error(
                verification.parsed.node,
                f"Failed to transpile the verification function {verification.name!r}",
                [error],
            )

        assert stmt is not None
        body.append(stmt)

    # NOTE (mristin):
    # We constrain the template parameters of the generic sequences here instead
    # of in the signature, see :py:func:`_generate_signature`.
    static_asserts: List[Stripped] = []
    for arg in verification.arguments:
        item_cls = intermediate.generic_sequence_item_class(arg)
        if item_cls is None:
            continue

        interface_name = (
            f"{cpp_common.TYPES_NAMESPACE}::{cpp_naming.interface_name(item_cls.name)}"
        )
        arg_name = cpp_naming.argument_name(arg.name)
        static_asserts.append(
            Stripped(
                f"""\
static_assert(
{I}std::is_base_of<{interface_name}, {_type_parameter_name(arg)}>::value,
{I}"Expected the items of {arg_name} to be instances of {interface_name}"
);"""
            )
        )

    body_joined = "\n".join([*static_asserts, *body])

    return (
        Stripped(
            f"""\
{_generate_signature(verification)} {{
{I}{indent_but_first_line(body_joined, I)}
}}"""
        ),
        None,
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
    type_inference: intermediate_type_inference.TypeInference,
    spec_impls: specific_implementations.SpecificImplementations,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate header of verification logic."""
    namespace = Stripped(f"{library_namespace}::verification")

    include_guard_var = cpp_common.include_guard_var(namespace)

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    # NOTE (mristin):
    # The public generic verification functions are templates, so we define them
    # in the header, see :py:func:`_is_generic`. Their bodies need the same
    # includes as the definitions in the implementation file.
    public_generic_verifications = [
        verification
        for verification in symbol_table.verification_functions
        if (
            verification.visibility is intermediate.Visibility.PUBLIC
            and _is_generic(verification)
        )
    ]

    our_includes = [
        f'#include "{include_prefix_path}/common.hpp"',
        f'#include "{include_prefix_path}/iteration.hpp"',
        f'#include "{include_prefix_path}/pattern.hpp"',
        f'#include "{include_prefix_path}/types.hpp"',
    ]

    std_includes = ["<set>"]
    if intermediate_uses.sets_in(symbol_table.verification_functions):
        std_includes.append("<unordered_set>")

    if len(public_generic_verifications) > 0:
        our_includes.extend(
            [
                f'#include "{include_prefix_path}/constants.hpp"',
                f'#include "{include_prefix_path}/stringification.hpp"',
            ]
        )

        std_includes.extend(["<memory>", "<type_traits>", "<vector>"])

        # NOTE (mristin):
        # See the includes in :py:func:`generate_implementation`.
        if intermediate_uses.abs_call(symbol_table):
            std_includes.extend(["<cmath>", "<cstdlib>"])

        if intermediate_uses.assert_statements_in(public_generic_verifications):
            std_includes.append("<stdexcept>")

    our_includes_joined = "\n".join(sorted(our_includes))
    std_includes_joined = "\n".join(
        f"#include {std_include}" for std_include in sorted(std_includes)
    )

    blocks: List[Stripped] = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            f"""\
{our_includes_joined}

#pragma warning(push, 0)
{std_includes_joined}
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            """\
/**
 * \\defgroup verification Verify that instances conform to the meta-model constraints.
 * @{
 */
namespace verification {"""
        ),
        Stripped(
            """\
// region Forward declarations
class Iterator;
class IVerification;

namespace impl {
class IVerificator;
}  // namespace impl
// endregion Forward declarations"""
        ),
        Stripped(
            f"""\
/**
 * Represent a verification error in an instance.
 */
struct Error {{
{I}/**
{I} * Human-readable description of the error
{I} */
{I}std::wstring cause;

{I}/**
{I} * Path to the erroneous value
{I} */
{I}iteration::Path path;

{I}explicit Error(std::wstring a_cause);
{I}Error(std::wstring a_cause, iteration::Path a_path);
}};  // struct Error"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Iterate over the verification errors.
 *
 * The user is expected to take ownership of the errors if they need to be further
 * processed.
 *
 * Unlike STL, this is <em>not</em> a light-weight iterator. We implement
 * a "yielding" iterator which keeps where it stopped in the model, so that
 * it looks for the next error only when you move it.
 *
 * This means that copy-construction and equality comparisons are much more heavy-weight
 * than you'd usually expect from an STL iterator. For example, if you want to sort
 * the errors by some criterion, you are most probably faster if you populate a vector,
 * and then sort the vector.
 *
 * Also, given that this iterator is not light-weight, you should in almost all cases
 * avoid the postfix increment (it++) and prefer the prefix one (++it) as the postfix
 * increment would create an iterator copy every time.
 *
 * We follow the C++ standard, and assume that comparison between the two iterators
 * over two different collections results in undefined behavior. See
 * http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2009/n2948.html and
 * https://stackoverflow.com/questions/4657513/comparing-iterators-from-different-containers.
 */
class Iterator {{
{I}using iterator_category = std::forward_iterator_tag;
{I}/// The difference is meaningless, but has to be defined.
{I}using difference_type = std::ptrdiff_t;
{I}using value_type = Error;
{I}using pointer = const Error*;
{I}using reference = const Error&;

 public:
{I}explicit Iterator(
{II}std::unique_ptr<impl::IVerificator> verificator
{I}) :
{I}verificator_(std::move(verificator)) {{
{II}  // Intentionally empty.
{I}}}

{I}Iterator(const Iterator& other);
{I}Iterator(Iterator&& other);

{I}Iterator& operator=(const Iterator& other);
{I}Iterator& operator=(Iterator&& other);

{I}reference operator*() const;
{I}pointer operator->() const;

{I}// Prefix increment
{I}Iterator& operator++();

{I}// Postfix increment
{I}Iterator operator++(int);

{I}friend bool operator==(const Iterator& a, const Iterator& b);
{I}friend bool operator!=(const Iterator& a, const Iterator& b);

 private:
{I}std::unique_ptr<impl::IVerificator> verificator_;
}};"""
        ),
        Stripped("bool operator==(const Iterator& a, const Iterator& b);"),
        Stripped("bool operator!=(const Iterator& a, const Iterator& b);"),
        Stripped(
            f"""\
/// \\cond HIDDEN
namespace impl {{
class IVerificator {{
 public:
{I}virtual void Start() = 0;
{I}virtual void Next() = 0;
{I}virtual bool Done() const = 0;

{I}virtual const Error& Get() const = 0;
{I}virtual Error& GetMutable() = 0;
{I}virtual long Index() const = 0;

{I}virtual std::unique_ptr<IVerificator> Clone() const = 0;

{I}virtual ~IVerificator() = default;
}};  // class IVerificator
}}  // namespace impl
/// \\endcond"""
        ),
        Stripped(
            f"""\
class IVerification {{
 public:
{I}virtual Iterator begin() const = 0;
{I}virtual const Iterator& end() const = 0;
{I}virtual ~IVerification() = default;
}};  // class IVerification"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Verify that the instance conforms to the meta-model constraints.
 *
 * Do not proceed to verify the instances referenced from
 * the given instance.
 *
 * Range-based loops should fit the vast majority of the use cases:
 * \\code
 * std::shared_ptr<types::Environment> env = ...;
 * for (const Error& error : NonRecursiveVerification(env)) {{
 * {I}report_somehow(error);
 * }}
 * \\endcode
 *
 * We use const references to shared pointers here for efficiency. Since
 * we do not make a copy of \\p that shared pointer, it is very important that
 * the given shared pointer outlives the verification, lest cause undefined behavior.
 * See these StackOverflow questions:
 * * https://stackoverflow.com/questions/12002480/passing-stdshared-ptr-to-constructors/12002668#12002668
 * * https://stackoverflow.com/questions/3310737/should-we-pass-a-shared-ptr-by-reference-or-by-value
 * * https://stackoverflow.com/questions/37610494/passing-const-shared-ptrt-versus-just-shared-ptrt-as-parameter
 */
class NonRecursiveVerification : public IVerification {{
 public:
{I}NonRecursiveVerification(
{II}const std::shared_ptr<types::IClass>& instance
{I});

{I}Iterator begin() const override;
{I}const Iterator& end() const override;

{I}~NonRecursiveVerification() override = default;
 private:
{I}const std::shared_ptr<types::IClass>& instance_;
}};  // class NonRecursiveVerification"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Verify that the instance conforms to the meta-model constraints.
 *
 * Also verify recursively all the instances referenced from
 * the given instance.
 *
 * Range-based loops should fit the vast majority of the use cases:
 * \\code
 * std::shared_ptr<types::Environment> env = ...;
 * for (const Error& error : RecursiveVerification(env)) {{
 * {I}report_somehow(error);
 * }}
 * \\endcode
 *
 * We use const references to shared pointers here for efficiency. Since
 * we do not make a copy of \\p that shared pointer, it is very important that
 * the given shared pointer outlives the verification, lest cause undefined behavior.
 * See these StackOverflow questions:
 * * https://stackoverflow.com/questions/12002480/passing-stdshared-ptr-to-constructors/12002668#12002668
 * * https://stackoverflow.com/questions/3310737/should-we-pass-a-shared-ptr-by-reference-or-by-value
 * * https://stackoverflow.com/questions/37610494/passing-const-shared-ptrt-versus-just-shared-ptrt-as-parameter
 */
class RecursiveVerification : public IVerification {{
 public:
{I}RecursiveVerification(
{II}const std::shared_ptr<types::IClass>& instance
{I});

{I}Iterator begin() const override;
{I}const Iterator& end() const override;

{I}~RecursiveVerification() override = default;
 private:
{I}const std::shared_ptr<types::IClass>& instance_;
}};  // class RecursiveVerification"""
        ),
    ]

    errors: List[Error] = []

    # NOTE (mristin):
    # The internal verification functions are declared only in the implementation
    # file so that they remain invisible to the users of the library.
    public_verifications = [
        verification
        for verification in symbol_table.verification_functions
        if verification.visibility is intermediate.Visibility.PUBLIC
    ]

    if len(public_verifications) > 0:
        blocks.append(Stripped("// region Verification functions"))

        for verification in public_verifications:
            block, error = _generate_verification_function_definition(
                verification=verification, spec_impls=spec_impls
            )
            if error is not None:
                errors.append(error)
                continue
            else:
                assert block is not None
                blocks.append(block)

        blocks.append(Stripped("// endregion Verification functions"))

    # NOTE (mristin):
    # The templates need to be defined in the header so that the users of
    # the library can instantiate them. We define them after all the declarations of
    # the verification functions, since the templates look up the functions which
    # they call at their definitions.
    if len(public_generic_verifications) > 0:
        blocks.append(
            Stripped("// region Definitions of generic verification functions")
        )

        for verification in public_generic_verifications:
            assert isinstance(verification, intermediate.TranspilableVerification)

            internal_call_errors = _check_no_calls_to_internal_verifications(
                verification=verification, symbol_table=symbol_table
            )
            if len(internal_call_errors) > 0:
                errors.extend(internal_call_errors)
                continue

            block, error = _generate_implementation_of_transpilable_verification(
                verification=verification,
                symbol_table=symbol_table,
                type_inference=type_inference,
            )
            if error is not None:
                errors.append(error)
                continue

            assert block is not None
            blocks.append(block)

        blocks.append(
            Stripped("// endregion Definitions of generic verification functions")
        )

    if len(symbol_table.constrained_primitives) > 0:
        blocks.append(Stripped("// region Verification of constrained primitives"))

        for constrained_primitive in symbol_table.constrained_primitives:
            blocks.append(
                _generate_definition_of_verify_constrained_primitive(
                    constrained_primitive=constrained_primitive
                )
            )

        blocks.append(Stripped("// endregion Verification of constrained primitives"))

    if len(errors) > 0:
        return None, errors

    blocks.extend(
        [
            Stripped(
                """\
}  // namespace verification
/**@}*/"""
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

    return out.getvalue(), None


def _generate_error_implementation() -> List[Stripped]:
    """Generate the implementation of the ``Error`` struct."""
    return [
        Stripped("// region struct Error"),
        Stripped(
            f"""\
Error::Error(
{I}std::wstring a_cause
) :
{I}cause(std::move(a_cause)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Error::Error(
{I}std::wstring a_cause,
{I}iteration::Path a_path
) :
{I}cause(std::move(a_cause)),
{I}path(std::move(a_path)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped("// endregion struct Error"),
    ]


def _generate_iterator_implementation() -> List[Stripped]:
    """Generate the implementation of the class ``Iterator``."""
    return [
        Stripped("// region struct Iterator"),
        Stripped(
            f"""\
Iterator::Iterator(
{I}const Iterator& other
) :
{I}verificator_(other.verificator_->Clone()) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Iterator::Iterator(
{I}Iterator&& other
) :
{I}verificator_(std::move(other.verificator_)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Iterator& Iterator::operator=(const Iterator& other) {{
{I}return *this = Iterator(other);
}}"""
        ),
        Stripped(
            f"""\
Iterator& Iterator::operator=(Iterator&& other) {{
{I}if (this != &other) {{
{II}verificator_ = std::move(other.verificator_);
{I}}}

{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
const Error& Iterator::operator*() const {{
{I}if (verificator_->Done()) {{
{II}throw std::logic_error(
{III}"You want to de-reference from a completed iterator "
{III}"over verification errors."
{II});
{I}}}

{I}return verificator_->Get();
}}"""
        ),
        Stripped(
            f"""\
const Error* Iterator::operator->() const {{
{I}if (verificator_->Done()) {{
{II}throw std::logic_error(
{III}"You want to de-reference from a completed iterator "
{III}"over verification errors."
{II});
{I}}}

{I}return &(verificator_->Get());
}}"""
        ),
        Stripped(
            f"""\
// Prefix increment
Iterator& Iterator::operator++() {{
{I}if (verificator_->Done()) {{
{II}throw std::logic_error(
{III}"You want to move a completed iterator "
{III}"over verification errors."
{II});
{I}}}

{I}verificator_->Next();
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
// Postfix increment
Iterator Iterator::operator++(int) {{
{I}Iterator result(*this);
{I}++(*this);
{I}return result;
}}"""
        ),
        Stripped(
            f"""\
bool operator==(const Iterator& a, const Iterator& b) {{
{I}return a.verificator_->Index() == b.verificator_->Index();
}}"""
        ),
        Stripped(
            f"""\
bool operator!=(const Iterator& a, const Iterator& b) {{
{I}return a.verificator_->Index() != b.verificator_->Index();
}}"""
        ),
        Stripped("// endregion struct Iterator"),
    ]


def _generate_pattern_verification_implementation(
    verification: intermediate.PatternVerification,
) -> Stripped:
    """Generate the implementation of the given pattern verification function."""
    assert len(verification.arguments) == 1
    arg = verification.arguments[0]

    arg_type = cpp_common.generate_type_with_const_ref_if_applicable(
        type_annotation=arg.type_annotation, types_namespace=cpp_common.TYPES_NAMESPACE
    )
    arg_name = cpp_naming.argument_name(arg.name)

    verification_name = cpp_naming.function_name(verification.name)

    program_name = cpp_naming.constant_name(Identifier(f"{verification.name}_program"))

    return Stripped(
        f"""\
bool {verification_name}(
{I}{indent_but_first_line(arg_type, I)} {arg_name}
) {{
{I}return revm::Match(
{II}pattern::{program_name},
{II}{arg_name}
{I});
}}"""
    )


class _InvariantTranspiler(cpp_transpilation.Transpiler):
    """
    Transpile invariants of the classes and of the constrained primitives.

    The ``self`` is transpiled to ``that``. For a class, ``that`` is a pointer to
    the instance, so that the members are accessed with ``->`` as for any other
    instance. For a constrained primitive, ``that`` is a reference to the value.
    """

    def __init__(
        self,
        type_map: Mapping[
            parse_tree.Node, intermediate_type_inference.TypeAnnotationUnion
        ],
        is_optional_map: Mapping[parse_tree.Node, bool],
        downcast_map: Mapping[parse_tree.Node, intermediate_type_inference.Downcast],
        is_optional_before_downcast_map: Mapping[parse_tree.Node, bool],
        environment: intermediate_type_inference.Environment,
        symbol_table: intermediate.SymbolTable,
    ) -> None:
        """Initialize with the given values."""
        cpp_transpilation.Transpiler.__init__(
            self,
            type_map=type_map,
            is_optional_map=is_optional_map,
            downcast_map=downcast_map,
            is_optional_before_downcast_map=is_optional_before_downcast_map,
            environment=environment,
            types_namespace=cpp_common.TYPES_NAMESPACE,
        )

        self._symbol_table = symbol_table

    def transform_name(
        self, node: parse_tree.Name
    ) -> Tuple[Optional[Stripped], Optional[Error]]:
        if node.identifier in self._variable_name_set:
            return Stripped(cpp_naming.variable_name(node.identifier)), None

        if node.identifier == "self":
            return Stripped("that"), None

        if node.identifier in self._symbol_table.constants_by_name:
            constant = cpp_naming.constant_name(node.identifier)
            return Stripped(f"{cpp_common.CONSTANTS_NAMESPACE}::{constant}"), None

        if node.identifier in self._symbol_table.verification_functions_by_name:
            # NOTE (mristin):
            # The invariants are checked in the anonymous namespace, where
            # the hand-written and the generated helpers would hide a verification
            # function of the same name, e.g., a verification function ``each``
            # would be hidden by the combinator ``Each``. Hence, we qualify.
            function_name = cpp_naming.function_name(node.identifier)
            return (
                Stripped(f"{cpp_common.VERIFICATION_NAMESPACE}::{function_name}"),
                None,
            )

        our_type = self._symbol_table.find_our_type(name=node.identifier)
        if isinstance(our_type, intermediate.Enumeration):
            return (
                Stripped(
                    f"{cpp_common.TYPES_NAMESPACE}::{cpp_naming.enum_name(node.identifier)}"
                ),
                None,
            )

        return None, Error(
            node.original_node,
            f"We can not determine how to transpile the name {node.identifier!r} "
            f"to C++. We could not find it neither in the local variables, "
            f"nor in the global constants, nor in verification functions, "
            f"nor as an enumeration. If you expect this name to be transpilable, "
            f"please contact the developers.",
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _transpile_invariant(
    invariant: intermediate.Invariant,
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """Translate the invariant from the meta-model into a C++ condition."""
    inference = type_inference.by_invariant[invariant]
    environment = inference.environment_with_self
    type_map = inference.type_map

    optional_inferrer = cpp_optionaling.Inferrer(
        environment=environment,
        type_map=type_map,
        downcast_map=inference.downcast_map,
    )

    _ = optional_inferrer.transform(invariant.body)

    if len(optional_inferrer.errors) > 0:
        return None, Error(
            invariant.parsed.node,
            "Failed to infer whether one or more nodes are ``common::optional`` "
            "in the invariant",
            optional_inferrer.errors,
        )

    transpiler = _InvariantTranspiler(
        type_map=type_map,
        is_optional_map=optional_inferrer.is_optional_map,
        downcast_map=inference.downcast_map,
        is_optional_before_downcast_map=(
            optional_inferrer.is_optional_before_downcast_map
        ),
        environment=environment,
        symbol_table=symbol_table,
    )

    expr, error = transpiler.transform(invariant.body)

    if error is not None:
        return None, error

    assert expr is not None
    return expr, None


# region Hand-written C++

# NOTE (mristin):
# The code below is written once by hand, and emitted verbatim. We emit a combinator
# only if the generated code uses it so that the compilers do not warn about unused
# functions in the anonymous namespace.

#: Define the check of a value, listed per shape in ``ChecksOf``.
_CHECK_STRUCT: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Represent a single check of a value.
 *
 * The checks of a shape are listed in \\ref ChecksOf.
 */
struct Check {{
{I}/**
{I} * Check that the invariant holds for the value
{I} */
{I}bool (*holds)(const void* value);

{I}/**
{I} * Human-readable description of the invariant, reported if it does not hold
{I} */
{I}const wchar_t* message;
}};  // struct Check"""
    ),
]


#: Define the interface of the lazy iterators over the values to verify.
_IITERATOR: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate lazily over the values to be verified.
 *
 * Every value comes with its \\ref Shape, which tells which checks apply to it.
 *
 * We build no paths while iterating. The path to the current value is built only
 * when an error has been found, see \\ref AppendToPath.
 *
 * The iterators are combined out of the combinators below. They follow three rules
 * so that we never build the iterators over the whole model up front:
 * 1. \\ref ChainIterator starts a child only once the previous child is done.
 * 2. \\ref DispatchingIterator dispatches on the instance only in \\ref Start.
 * 3. \\ref EachIterator builds the iterator over an item only once the iteration
 *    reaches the item.
 *
 * Under these rules, every combinator is cheap to construct eagerly.
 */
class IIterator {{
 public:
{I}/**
{I} * Position at the first value, or become done if there are no values.
{I} */
{I}virtual void Start() = 0;

{I}/**
{I} * Move to the next value, or become done if there are no more values.
{I} */
{I}virtual void Next() = 0;

{I}virtual bool Done() const = 0;

{I}/**
{I} * \\brief Point to the current value.
{I} *
{I} * The pointer is valid only until the next call to \\ref Next.
{I} */
{I}virtual const void* Value() const = 0;

{I}virtual Shape ShapeOf() const = 0;

{I}/**
{I} * \\brief Append the segments leading to the current value to the \\p path.
{I} *
{I} * Only called when an error is found, so the iteration itself builds no paths.
{I} */
{I}virtual void AppendToPath(iteration::Path& path) const = 0;

{I}virtual std::unique_ptr<IIterator> Clone() const = 0;

{I}virtual ~IIterator() = default;
}};  // class IIterator"""
    ),
]


#: Define the iterator over no values.
_EMPTY: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Iterate over no values at all.
 */
class EmptyIterator : public IIterator {{
 public:
{I}void Start() override {{
{II}// Intentionally empty.
{I}}}

{I}void Next() override {{
{II}throw std::logic_error(
{III}"You want to move an EmptyIterator, but it is always done."
{II});
{I}}}

{I}bool Done() const override {{
{II}return true;
{I}}}

{I}const void* Value() const override {{
{II}throw std::logic_error(
{III}"You want to get a value from an EmptyIterator, but it is always done."
{II});
{I}}}

{I}Shape ShapeOf() const override {{
{II}throw std::logic_error(
{III}"You want to get a shape from an EmptyIterator, but it is always done."
{II});
{I}}}

{I}void AppendToPath(iteration::Path&) const override {{
{II}throw std::logic_error(
{III}"You want to append the path of an EmptyIterator, but it is always done."
{II});
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<EmptyIterator>(*this);
{I}}}
}};  // class EmptyIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<IIterator> Empty() {{
{I}return common::make_unique<EmptyIterator>();
}}"""
    ),
]


#: Define the iterator over a single value which lives in the model.
_ONE: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Iterate over a single value which lives in the model.
 */
class OneIterator : public IIterator {{
 public:
{I}OneIterator(
{II}const void* value,
{II}Shape shape
{I}) :
{II}value_(value),
{II}shape_(shape),
{II}done_(true) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}done_ = false;
{I}}}

{I}void Next() override {{
{II}done_ = true;
{I}}}

{I}bool Done() const override {{
{II}return done_;
{I}}}

{I}const void* Value() const override {{
{II}return value_;
{I}}}

{I}Shape ShapeOf() const override {{
{II}return shape_;
{I}}}

{I}void AppendToPath(iteration::Path&) const override {{
{II}// Intentionally empty, as the value itself is the end of the path.
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<OneIterator>(*this);
{I}}}

 private:
{I}const void* value_;
{I}Shape shape_;
{I}bool done_;
}};  // class OneIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<IIterator> One(
{I}const void* value,
{I}Shape shape
) {{
{I}return common::make_unique<OneIterator>(value, shape);
}}"""
    ),
]


#: Define the iterator over a single value of which we keep a copy.
_ONE_BY_VALUE: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over a single value which we keep a copy of.
 *
 * The getters of booleans, integers and floating-point numbers return by value,
 * so these values have no address in the model which we could point to.
 */
template<typename T>
class OneByValueIterator : public IIterator {{
 public:
{I}OneByValueIterator(
{II}T value,
{II}Shape shape
{I}) :
{II}value_(value),
{II}shape_(shape),
{II}done_(true) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}done_ = false;
{I}}}

{I}void Next() override {{
{II}done_ = true;
{I}}}

{I}bool Done() const override {{
{II}return done_;
{I}}}

{I}const void* Value() const override {{
{II}return &value_;
{I}}}

{I}Shape ShapeOf() const override {{
{II}return shape_;
{I}}}

{I}void AppendToPath(iteration::Path&) const override {{
{II}// Intentionally empty, as the value itself is the end of the path.
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<OneByValueIterator<T> >(*this);
{I}}}

 private:
{I}T value_;
{I}Shape shape_;
{I}bool done_;
}};  // class OneByValueIterator"""
    ),
    Stripped(
        f"""\
template<typename T>
std::unique_ptr<IIterator> OneByValue(
{I}T value,
{I}Shape shape
) {{
{I}return common::make_unique<OneByValueIterator<T> >(value, shape);
}}"""
    ),
]


#: Define the iterator over the children, one after another.
_CHAIN: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the values of the children, one child after another.
 *
 * A child is started only once the previous child is done.
 */
class ChainIterator : public IIterator {{
 public:
{I}explicit ChainIterator(
{II}std::vector<std::unique_ptr<IIterator> > children
{I}) :
{II}children_(std::move(children)),
{II}active_(0) {{
{II}// Intentionally empty.
{I}}}

{I}ChainIterator(const ChainIterator& other) :
{II}active_(other.active_) {{
{II}children_.reserve(other.children_.size());
{II}for (const std::unique_ptr<IIterator>& child : other.children_) {{
{III}children_.emplace_back(child->Clone());
{II}}}
{I}}}

{I}void Start() override {{
{II}active_ = 0;
{II}if (!children_.empty()) {{
{III}children_[0]->Start();
{II}}}
{II}SkipDoneChildren();
{I}}}

{I}void Next() override {{
{II}children_[active_]->Next();
{II}SkipDoneChildren();
{I}}}

{I}bool Done() const override {{
{II}return active_ >= children_.size();
{I}}}

{I}const void* Value() const override {{
{II}return children_[active_]->Value();
{I}}}

{I}Shape ShapeOf() const override {{
{II}return children_[active_]->ShapeOf();
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}children_[active_]->AppendToPath(path);
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<ChainIterator>(*this);
{I}}}

 private:
{I}std::vector<std::unique_ptr<IIterator> > children_;

{I}/**
{I} * Index of the child we currently iterate over
{I} */
{I}std::size_t active_;

{I}/**
{I} * Move on to the next children, and start them, until one is not done.
{I} */
{I}void SkipDoneChildren() {{
{II}while (active_ < children_.size() && children_[active_]->Done()) {{
{III}++active_;
{III}if (active_ < children_.size()) {{
{IIII}children_[active_]->Start();
{III}}}
{II}}}
{I}}}
}};  // class ChainIterator"""
    ),
    Stripped(
        f"""\
void CollectChildren(
{I}std::vector<std::unique_ptr<IIterator> >&
) {{
{I}// Intentionally empty, as there are no more children to collect.
}}"""
    ),
    Stripped(
        f"""\
template<typename... Rest>
void CollectChildren(
{I}std::vector<std::unique_ptr<IIterator> >& children,
{I}std::unique_ptr<IIterator> first,
{I}Rest... rest
) {{
{I}children.emplace_back(std::move(first));
{I}CollectChildren(children, std::move(rest)...);
}}"""
    ),
    Stripped(
        f"""\
// NOTE (mristin):
// We can not use an initializer list here, as we can not move the unique pointers
// out of it.
template<typename... Children>
std::unique_ptr<IIterator> Chain(
{I}Children... children
) {{
{I}std::vector<std::unique_ptr<IIterator> > collected;
{I}collected.reserve(sizeof...(Children));
{I}CollectChildren(collected, std::move(children)...);

{I}return common::make_unique<ChainIterator>(std::move(collected));
}}"""
    ),
]


#: Define the iterator over the values in a property.
_IN_PROPERTY: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Iterate over the values of the \\p child, which lives in a property.
 */
class InPropertyIterator : public IIterator {{
 public:
{I}InPropertyIterator(
{II}iteration::Property property,
{II}std::unique_ptr<IIterator> child
{I}) :
{II}property_(property),
{II}child_(std::move(child)) {{
{II}// Intentionally empty.
{I}}}

{I}InPropertyIterator(const InPropertyIterator& other) :
{II}property_(other.property_),
{II}child_(other.child_->Clone()) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}child_->Start();
{I}}}

{I}void Next() override {{
{II}child_->Next();
{I}}}

{I}bool Done() const override {{
{II}return child_->Done();
{I}}}

{I}const void* Value() const override {{
{II}return child_->Value();
{I}}}

{I}Shape ShapeOf() const override {{
{II}return child_->ShapeOf();
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<iteration::PropertySegment>(property_)
{II});
{II}child_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<InPropertyIterator>(*this);
{I}}}

 private:
{I}iteration::Property property_;
{I}std::unique_ptr<IIterator> child_;
}};  // class InPropertyIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<IIterator> InProperty(
{I}iteration::Property property,
{I}std::unique_ptr<IIterator> child
) {{
{I}return common::make_unique<InPropertyIterator>(property, std::move(child));
}}"""
    ),
]


#: Define the iterator over the values in a component of a tuple.
_AT_INDEX: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Iterate over the values of the \\p child, which lives in a component of a tuple.
 */
class AtIndexIterator : public IIterator {{
 public:
{I}AtIndexIterator(
{II}std::size_t index,
{II}std::unique_ptr<IIterator> child
{I}) :
{II}index_(index),
{II}child_(std::move(child)) {{
{II}// Intentionally empty.
{I}}}

{I}AtIndexIterator(const AtIndexIterator& other) :
{II}index_(other.index_),
{II}child_(other.child_->Clone()) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}child_->Start();
{I}}}

{I}void Next() override {{
{II}child_->Next();
{I}}}

{I}bool Done() const override {{
{II}return child_->Done();
{I}}}

{I}const void* Value() const override {{
{II}return child_->Value();
{I}}}

{I}Shape ShapeOf() const override {{
{II}return child_->ShapeOf();
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<iteration::IndexSegment>(index_)
{II});
{II}child_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<AtIndexIterator>(*this);
{I}}}

 private:
{I}std::size_t index_;
{I}std::unique_ptr<IIterator> child_;
}};  // class AtIndexIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<IIterator> AtIndex(
{I}std::size_t index,
{I}std::unique_ptr<IIterator> child
) {{
{I}return common::make_unique<AtIndexIterator>(index, std::move(child));
}}"""
    ),
]


#: Define the iterator over the items of a list.
_EACH: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the values of every item of a list, one item after another.
 *
 * The iterator over an item is built only once the iteration reaches the item.
 */
template<typename T>
class EachIterator : public IIterator {{
 public:
{I}/**
{I} * Build the iterator over the values of an item
{I} */
{I}typedef std::unique_ptr<IIterator> (*OverItem)(const T& item, bool recursive);

{I}EachIterator(
{II}const std::vector<T>* items,
{II}OverItem over_item,
{II}bool recursive
{I}) :
{II}items_(items),
{II}over_item_(over_item),
{II}recursive_(recursive),
{II}index_(0) {{
{II}// Intentionally empty.
{I}}}

{I}EachIterator(const EachIterator<T>& other) :
{II}items_(other.items_),
{II}over_item_(other.over_item_),
{II}recursive_(other.recursive_),
{II}index_(other.index_),
{II}item_(other.item_ == nullptr ? nullptr : other.item_->Clone()) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}index_ = 0;
{II}item_ = nullptr;
{II}SkipDoneItems();
{I}}}

{I}void Next() override {{
{II}item_->Next();
{II}SkipDoneItems();
{I}}}

{I}bool Done() const override {{
{II}return index_ >= items_->size();
{I}}}

{I}const void* Value() const override {{
{II}return item_->Value();
{I}}}

{I}Shape ShapeOf() const override {{
{II}return item_->ShapeOf();
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<iteration::IndexSegment>(index_)
{II});
{II}item_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<EachIterator<T> >(*this);
{I}}}

 private:
{I}const std::vector<T>* items_;
{I}OverItem over_item_;
{I}bool recursive_;

{I}/**
{I} * Index of the item we currently iterate over
{I} */
{I}std::size_t index_;

{I}/**
{I} * Iterator over the current item, built once we reached the item
{I} */
{I}std::unique_ptr<IIterator> item_;

{I}/**
{I} * Move on to the next items, and build their iterators, until one is not done.
{I} */
{I}void SkipDoneItems() {{
{II}while (index_ < items_->size()) {{
{III}if (item_ == nullptr) {{
{IIII}item_ = over_item_((*items_)[index_], recursive_);
{IIII}item_->Start();
{III}}}

{III}if (!item_->Done()) {{
{IIII}return;
{III}}}

{III}item_ = nullptr;
{III}++index_;
{II}}}
{I}}}
}};  // class EachIterator"""
    ),
    Stripped(
        f"""\
template<typename T>
std::unique_ptr<IIterator> Each(
{I}const std::vector<T>& items,
{I}std::unique_ptr<IIterator> (*over_item)(const T& item, bool recursive),
{I}bool recursive
) {{
{I}return common::make_unique<EachIterator<T> >(&items, over_item, recursive);
}}"""
    ),
]


#: Define the iterator over the items of a set, in the order of the serialization.
_EACH_SORTED: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the values of every item of a set, one item after
 * another, in the order in which we serialize the set.
 *
 * The index in the path of an error is the index of the item in the serialized
 * array. The items are sorted only once the iteration starts, and the iterator
 * over an item is built only once the iteration reaches the item.
 */
template<typename T, typename HashT, typename LessT>
class EachSortedIterator : public IIterator {{
 public:
{I}/**
{I} * Build the iterator over the values of an item
{I} */
{I}typedef std::unique_ptr<IIterator> (*OverItem)(const T& item, bool recursive);

{I}EachSortedIterator(
{II}const std::unordered_set<T, HashT>* items,
{II}LessT less,
{II}OverItem over_item,
{II}bool recursive
{I}) :
{II}items_(items),
{II}less_(less),
{II}over_item_(over_item),
{II}recursive_(recursive),
{II}index_(0) {{
{II}// Intentionally empty.
{I}}}

{I}EachSortedIterator(const EachSortedIterator<T, HashT, LessT>& other) :
{II}items_(other.items_),
{II}less_(other.less_),
{II}over_item_(other.over_item_),
{II}recursive_(other.recursive_),
{II}sorted_(other.sorted_),
{II}index_(other.index_),
{II}item_(other.item_ == nullptr ? nullptr : other.item_->Clone()) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}if (sorted_ == nullptr) {{
{III}sorted_ = std::make_shared<std::vector<const T*> >(
{IIII}common::SortedPointers(*items_, less_)
{III});
{II}}}

{II}index_ = 0;
{II}item_ = nullptr;
{II}SkipDoneItems();
{I}}}

{I}void Next() override {{
{II}item_->Next();
{II}SkipDoneItems();
{I}}}

{I}bool Done() const override {{
{II}return index_ >= sorted_->size();
{I}}}

{I}const void* Value() const override {{
{II}return item_->Value();
{I}}}

{I}Shape ShapeOf() const override {{
{II}return item_->ShapeOf();
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<iteration::IndexSegment>(index_)
{II});
{II}item_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<EachSortedIterator<T, HashT, LessT> >(*this);
{I}}}

 private:
{I}const std::unordered_set<T, HashT>* items_;
{I}LessT less_;
{I}OverItem over_item_;
{I}bool recursive_;

{I}/**
{I} * Pointers to the items, sorted once the iteration started, and shared among
{I} * the clones as they never change
{I} */
{I}std::shared_ptr<const std::vector<const T*> > sorted_;

{I}/**
{I} * Index of the item we currently iterate over, in the sorted order
{I} */
{I}std::size_t index_;

{I}/**
{I} * Iterator over the current item, built once we reached the item
{I} */
{I}std::unique_ptr<IIterator> item_;

{I}/**
{I} * Move on to the next items, and build their iterators, until one is not done.
{I} */
{I}void SkipDoneItems() {{
{II}while (index_ < sorted_->size()) {{
{III}if (item_ == nullptr) {{
{IIII}item_ = over_item_(*(*sorted_)[index_], recursive_);
{IIII}item_->Start();
{III}}}

{III}if (!item_->Done()) {{
{IIII}return;
{III}}}

{III}item_ = nullptr;
{III}++index_;
{II}}}
{I}}}
}};  // class EachSortedIterator"""
    ),
    Stripped(
        f"""\
template<typename T, typename HashT, typename LessT>
std::unique_ptr<IIterator> EachSorted(
{I}const std::unordered_set<T, HashT>& items,
{I}LessT less,
{I}std::unique_ptr<IIterator> (*over_item)(const T& item, bool recursive),
{I}bool recursive
) {{
{I}return common::make_unique<EachSortedIterator<T, HashT, LessT> >(
{II}&items, less, over_item, recursive
{I});
}}"""
    ),
]


#: Define the iterator over the instances referenced from another one.
_OVER: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the values of an instance, dispatched on its runtime type.
 *
 * Defined below, once all the classes have been covered.
 */
std::unique_ptr<IIterator> DispatchOnModelType(
{I}const types::IClass& instance,
{I}bool recursive
);"""
    ),
    Stripped(
        f"""\
/**
 * \\brief Iterate recursively over the values of an instance referenced from
 * another instance.
 *
 * We dispatch on the runtime type of the instance only in \\ref Start so that
 * we descend into the instance only once the iteration reaches it.
 */
class DispatchingIterator : public IIterator {{
 public:
{I}explicit DispatchingIterator(
{II}const types::IClass* instance
{I}) :
{II}instance_(instance) {{
{II}// Intentionally empty.
{I}}}

{I}DispatchingIterator(const DispatchingIterator& other) :
{II}instance_(other.instance_),
{II}child_(other.child_ == nullptr ? nullptr : other.child_->Clone()) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}child_ = DispatchOnModelType(*instance_, true);
{II}child_->Start();
{I}}}

{I}void Next() override {{
{II}child_->Next();
{I}}}

{I}bool Done() const override {{
{II}return child_->Done();
{I}}}

{I}const void* Value() const override {{
{II}return child_->Value();
{I}}}

{I}Shape ShapeOf() const override {{
{II}return child_->ShapeOf();
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}child_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<DispatchingIterator>(*this);
{I}}}

 private:
{I}const types::IClass* instance_;
{I}std::unique_ptr<IIterator> child_;
}};  // class DispatchingIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<IIterator> Over(
{I}const types::IClass& instance,
{I}bool recursive
) {{
{I}if (!recursive) {{
{II}// NOTE (mristin):
{II}// In the non-recursive mode, we verify only the instance itself, but not
{II}// the instances that it references.
{II}return Empty();
{I}}}

{I}return common::make_unique<DispatchingIterator>(&instance);
}}"""
    ),
    Stripped(
        f"""\
template<typename T>
std::unique_ptr<IIterator> ThroughPointer(
{I}const std::shared_ptr<T>& instance,
{I}bool recursive
) {{
{I}return Over(*instance, recursive);
}}"""
    ),
]


#: Define the iterator over the keys of a JSON-able object.
_EACH_KEY: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the keys of a JSON-able object as values of the given shape.
 *
 * We iterate over nothing if the value is not an object, as the verification of
 * the value itself is not the concern of this iterator.
 */
class EachKeyIterator : public IIterator {{
 public:
{I}EachKeyIterator(
{II}const nlohmann::json* object,
{II}Shape shape
{I}) :
{II}object_(object),
{II}shape_(shape),
{II}done_(true) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}if (!object_->is_object()) {{
{III}done_ = true;
{III}return;
{II}}}

{II}it_ = object_->cbegin();
{II}ConvertKey();
{I}}}

{I}void Next() override {{
{II}++it_;
{II}ConvertKey();
{I}}}

{I}bool Done() const override {{
{II}return done_;
{I}}}

{I}const void* Value() const override {{
{II}return &key_;
{I}}}

{I}Shape ShapeOf() const override {{
{II}return shape_;
{I}}}

{I}void AppendToPath(iteration::Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<iteration::KeySegment>(key_)
{II});
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<EachKeyIterator>(*this);
{I}}}

 private:
{I}const nlohmann::json* object_;
{I}Shape shape_;
{I}bool done_;
{I}nlohmann::json::const_iterator it_;

{I}/**
{I} * \\brief Current key, converted from UTF-8.
{I} *
{I} * The keys of a JSON-able object are UTF-8 strings, while the constrained
{I} * primitives expect wide strings, so we convert one key at a time.
{I} */
{I}std::wstring key_;

{I}/**
{I} * Convert the key at the iterator, or become done at the end of the object.
{I} */
{I}void ConvertKey() {{
{II}done_ = it_ == object_->cend();
{II}if (!done_) {{
{III}key_ = common::Utf8ToWstring(it_.key());
{II}}}
{I}}}
}};  // class EachKeyIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<IIterator> EachKey(
{I}const nlohmann::json& object,
{I}Shape shape
) {{
{I}return common::make_unique<EachKeyIterator>(&object, shape);
}}"""
    ),
]


#: Define the iterator over the errors, and its start and end.
_ERROR_ITERATOR: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the errors of the values, one error at a time.
 *
 * For every value, we first run the checks of its shape, each reporting at most
 * one error. Then we run the nested verification of the value, if its shape has
 * one, which can report many errors, see \\ref NewNestedVerificator.
 *
 * We do only the work needed to find the next error, and build the path to
 * the erroneous value only once an error has been found.
 */
class ErrorIterator : public impl::IVerificator {{
 public:
{I}explicit ErrorIterator(
{II}std::unique_ptr<IIterator> values
{I}) :
{II}values_(std::move(values)),
{II}check_(0),
{II}nested_started_(false),
{II}index_(-1) {{
{II}// Intentionally empty.
{I}}}

{I}ErrorIterator(const ErrorIterator& other) :
{II}values_(other.values_->Clone()),
{II}check_(other.check_),
{II}nested_started_(other.nested_started_),
{II}nested_(other.nested_ == nullptr ? nullptr : other.nested_->Clone()),
{II}error_(other.error_),
{II}index_(other.index_) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}values_->Start();
{II}check_ = 0;
{II}nested_started_ = false;
{II}nested_ = nullptr;
{II}index_ = -1;

{II}Advance();
{I}}}

{I}void Next() override {{
{II}#ifdef DEBUG
{II}if (Done()) {{
{III}throw std::logic_error(
{IIII}"You want to move an ErrorIterator, but it was done."
{III});
{II}}}
{II}#endif

{II}Advance();
{I}}}

{I}bool Done() const override {{
{II}return values_->Done();
{I}}}

{I}const Error& Get() const override {{
{II}#ifdef DEBUG
{II}if (Done()) {{
{III}throw std::logic_error(
{IIII}"You want to get from an ErrorIterator, but it was done."
{III});
{II}}}
{II}#endif

{II}return *error_;
{I}}}

{I}Error& GetMutable() override {{
{II}#ifdef DEBUG
{II}if (Done()) {{
{III}throw std::logic_error(
{IIII}"You want to get mutable from an ErrorIterator, but it was done."
{III});
{II}}}
{II}#endif

{II}return *error_;
{I}}}

{I}long Index() const override {{
{II}return index_;
{I}}}

{I}std::unique_ptr<impl::IVerificator> Clone() const override {{
{II}return common::make_unique<ErrorIterator>(*this);
{I}}}

 private:
{I}std::unique_ptr<IIterator> values_;

{I}/**
{I} * Index of the next check to run on the current value
{I} */
{I}std::size_t check_;

{I}/**
{I} * Set if we already started the nested verification of the current value
{I} */
{I}bool nested_started_;

{I}/**
{I} * Nested verification of the current value, if its shape has one
{I} */
{I}std::unique_ptr<impl::IVerificator> nested_;

{I}common::optional<Error> error_;

{I}/**
{I} * Index of the current error, -1 if done
{I} */
{I}long index_;

{I}/**
{I} * Move on to the next error, or become done if there are no more errors.
{I} */
{I}void Advance() {{
{II}while (!values_->Done()) {{
{III}const void* value = values_->Value();
{III}const Shape shape = values_->ShapeOf();

{III}const std::vector<Check>& checks = ChecksOf(shape);
{III}while (check_ < checks.size()) {{
{IIII}const Check& check = checks[check_];
{IIII}++check_;

{IIII}if (!check.holds(value)) {{
{IIIII}error_ = Error(check.message);
{IIIII}values_->AppendToPath(error_->path);
{IIIII}++index_;
{IIIII}return;
{IIII}}}
{III}}}

{III}// NOTE (mristin):
{III}// All the checks of the value have been run. We now either start the nested
{III}// verification of the value, or resume it where we stopped at its last error.
{III}if (!nested_started_) {{
{IIII}nested_started_ = true;
{IIII}nested_ = NewNestedVerificator(shape, value);
{IIII}if (nested_ != nullptr) {{
{IIIII}nested_->Start();
{IIII}}}
{III}}} else if (nested_ != nullptr) {{
{IIII}nested_->Next();
{III}}}

{III}if (nested_ != nullptr && !nested_->Done()) {{
{IIII}// NOTE (mristin):
{IIII}// The path of the nested error is relative to the value, so we prefix it
{IIII}// with the path to the value. We take over the data members of the nested
{IIII}// error to avoid a costly copy, as we move the nested verification on
{IIII}// before we look at its error again.
{IIII}Error& nested_error = nested_->GetMutable();

{IIII}error_ = Error(std::move(nested_error.cause));
{IIII}values_->AppendToPath(error_->path);
{IIII}for (
{IIIII}std::unique_ptr<iteration::ISegment>& segment
{IIIII}: nested_error.path.segments
{IIII}) {{
{IIIII}error_->path.segments.emplace_back(std::move(segment));
{IIII}}}

{IIII}++index_;
{IIII}return;
{III}}}

{III}values_->Next();
{III}check_ = 0;
{III}nested_started_ = false;
{III}nested_ = nullptr;
{II}}}

{II}error_ = common::nullopt;
{II}index_ = -1;
{I}}}
}};  // class ErrorIterator"""
    ),
    Stripped(
        f"""\
/**
 * Start iterating over the errors of the \\p values.
 */
Iterator IterateErrors(
{I}std::unique_ptr<IIterator> values
) {{
{I}std::unique_ptr<impl::IVerificator> verificator(
{II}common::make_unique<ErrorIterator>(std::move(values))
{I});
{I}verificator->Start();

{I}return Iterator(std::move(verificator));
}}"""
    ),
    Stripped(
        f"""\
/**
 * Give out the iterator past the last error, shared by all the verifications.
 */
const Iterator& PastLastError() {{
{I}static const Iterator iterator(IterateErrors(Empty()));
{I}return iterator;
}}"""
    ),
]


#: Define the verification of the values given by an iterator.
_VALUES_VERIFICATION: Final[Sequence[Stripped]] = [
    Stripped(
        f"""\
/**
 * Verify the values given by the iterator, which we restart on every \\ref begin.
 */
class ValuesVerification : public IVerification {{
 public:
{I}explicit ValuesVerification(
{II}std::unique_ptr<IIterator> values
{I}) :
{II}values_(std::move(values)) {{
{II}// Intentionally empty.
{I}}}

{I}Iterator begin() const override {{
{II}return IterateErrors(values_->Clone());
{I}}}

{I}const Iterator& end() const override {{
{II}return PastLastError();
{I}}}

{I}~ValuesVerification() override = default;

 private:
{I}std::unique_ptr<IIterator> values_;
}};  // class ValuesVerification"""
    ),
]

# endregion Hand-written C++


class _Analysis:
    """Determine which values we have to verify at all."""

    #: Constrained primitives with at least one invariant, including the inherited
    #: ones, as runtime IDs
    checked_constrained_primitive_id_set: Final[Set[int]]

    #: Concrete classes whose instances have anything to verify, either themselves
    #: or in the values they (recursively) reference, as runtime IDs
    yielding_class_id_set: Final[Set[int]]

    def __init__(self, symbol_table: intermediate.SymbolTable) -> None:
        """Analyze the ``symbol_table``."""
        self.checked_constrained_primitive_id_set = {
            id(constrained_primitive)
            for constrained_primitive in symbol_table.constrained_primitives
            if len(constrained_primitive.invariants) > 0
        }

        self.yielding_class_id_set = set()

        # NOTE (mristin):
        # The classes can reference each other in cycles, so we compute the fixed
        # point. The set can only grow, so the loop terminates.
        changed = True
        while changed:
            changed = False
            for cls in symbol_table.concrete_classes:
                if id(cls) in self.yielding_class_id_set:
                    continue

                if len(cls.invariants) > 0 or any(
                    self.yields(prop.type_annotation, descend=True)
                    for prop in cls.properties
                ):
                    self.yielding_class_id_set.add(id(cls))
                    changed = True

    def yields(
        self, type_annotation: intermediate.TypeAnnotationUnion, descend: bool
    ) -> bool:
        """
        Check whether a value of ``type_annotation`` has anything to verify.

        If ``descend`` is not set, we ignore the instances of classes, as in
        the non-recursive verification.
        """
        if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
            return False

        elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
            our_type = type_annotation.our_type

            if isinstance(our_type, intermediate.Enumeration):
                return False

            elif isinstance(our_type, intermediate.ConstrainedPrimitive):
                return id(our_type) in self.checked_constrained_primitive_id_set

            elif isinstance(our_type, intermediate.Class):
                concrete_classes = list(our_type.concrete_descendants)
                if isinstance(our_type, intermediate.ConcreteClass):
                    concrete_classes.append(our_type)

                return descend and any(
                    id(cls) in self.yielding_class_id_set for cls in concrete_classes
                )

            elif isinstance(our_type, intermediate.NamedUnion):
                return descend and any(
                    id(cls) in self.yielding_class_id_set
                    for cls in our_type.implementers
                )

            else:
                assert_never(our_type)

        elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
            return self.yields(type_annotation.value, descend=descend)

        elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
            return self.yields(type_annotation.items, descend=descend)

        elif isinstance(type_annotation, intermediate.SetTypeAnnotation):
            return self.yields(type_annotation.items, descend=descend)

        elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
            return any(
                self.yields(item, descend=descend) for item in type_annotation.items
            )

        elif isinstance(
            type_annotation,
            (
                intermediate.JsonValueTypeAnnotation,
                intermediate.JsonArrayTypeAnnotation,
                intermediate.JsonObjectTypeAnnotation,
            ),
        ):
            return True

        else:
            assert_never(type_annotation)

        raise AssertionError("Unexpected execution path")

    def yields_recursively(
        self, type_annotation: intermediate.TypeAnnotationUnion
    ) -> bool:
        """Check whether a value of ``type_annotation`` has anything to verify."""
        return self.yields(type_annotation, descend=True)


# NOTE (mristin):
# The literals of our types come from :py:func:`cpp_naming.enum_literal_name`,
# which capitalizes only the first letter of every part of a name. The literals
# of JSON-able values contain an upper-case abbreviation, so that they never
# clash with the literals of our types by construction, even though the parser
# reserves names such as ``Json_object`` anyhow.
_JSON_SHAPE_LITERALS = (
    Identifier("kJSONValue"),
    Identifier("kJSONArray"),
    Identifier("kJSONObject"),
)


def _shape_literal(
    our_type: Union[intermediate.ConstrainedPrimitive, intermediate.ConcreteClass]
) -> Identifier:
    """Generate the literal of ``Shape`` for the values of ``our_type``."""
    return cpp_naming.enum_literal_name(our_type.name)


def _json_shape_literal(
    type_annotation: Union[
        intermediate.JsonValueTypeAnnotation,
        intermediate.JsonArrayTypeAnnotation,
        intermediate.JsonObjectTypeAnnotation,
    ]
) -> Identifier:
    """Generate the literal of ``Shape`` for the JSON-able values."""
    if isinstance(type_annotation, intermediate.JsonValueTypeAnnotation):
        return _JSON_SHAPE_LITERALS[0]
    elif isinstance(type_annotation, intermediate.JsonArrayTypeAnnotation):
        return _JSON_SHAPE_LITERALS[1]
    elif isinstance(type_annotation, intermediate.JsonObjectTypeAnnotation):
        return _JSON_SHAPE_LITERALS[2]
    else:
        assert_never(type_annotation)


# region Iteration over the values

# NOTE (mristin):
# We generate the iteration over the values in two passes, see the module
# :py:mod:`aas_core_codegen.cpp.over` for the naming and the collection of
# the generated functions.


# fmt: off
@require(
    lambda type_annotation, analysis, function_name_set:
    all(
        cpp_over.over_function_name(referenced) in function_name_set
        for referenced in cpp_over.referenced_function_types(type_annotation, analysis.yields_recursively)
    ),
    "The functions over the referenced types have been collected"
)
@ensure(
    lambda function_name_set, result:
    result is None
    or cpp_over.called_function_names(result, defined="").issubset(function_name_set),
    "The expression calls only the collected functions"
)
# fmt: on
def _generate_over_expression(
    type_annotation: intermediate.TypeAnnotationUnion,
    expr: str,
    by_value: bool,
    analysis: _Analysis,
    function_name_set: AbstractSet[str],
) -> Optional[Stripped]:
    """
    Generate the iterator over the values in ``expr`` of ``type_annotation``.

    The ``expr`` is the C++ expression of the value, for example:

    * ``that.some_names()`` for a property of the class (``that`` is the instance),
    * ``(*that.semantic_id())`` for the value of an optional property,
    * ``std::get<1>(value)`` for a component of a tuple, and
    * ``value`` for an item of a list.

    For example, we generate for a property ``name: Name_type``:

    .. code-block:: cpp

        One(&that.name(), Shape::kNameType)

    for a property ``semantic_id: Optional[Reference]``:

    .. code-block:: cpp

        that.semantic_id().has_value()
          ? Over(*(*that.semantic_id()), recursive)
          : Empty()

    and for a property ``some_names: List[Name]``:

    .. code-block:: cpp

        Over_listOf_Name(that.some_names(), recursive)

    If ``by_value`` is set, the ``expr`` has no address, as the getters return
    booleans, integers and floating-point numbers by value, so we keep a copy:

    .. code-block:: cpp

        OneByValue(that.some_int(), Shape::kPositiveInt)

    The ``function_name_set`` contains the names of the collected functions over
    the lists, tuples and named unions, see :py:func:`cpp_over.collect_function_types`.

    Return ``None`` if there is nothing to verify in a value of
    the ``type_annotation``.
    """
    if not analysis.yields(type_annotation, descend=True):
        return None

    if isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        inner = _generate_over_expression(
            type_annotation=type_annotation.value,
            expr=f"(*{expr})",
            by_value=False,
            analysis=analysis,
            function_name_set=function_name_set,
        )
        assert inner is not None

        return Stripped(
            f"""\
{expr}.has_value()
{I}? {indent_but_first_line(inner, II)}
{I}: Empty()"""
        )

    elif isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        raise AssertionError("Primitive values have nothing to verify")

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        our_type = type_annotation.our_type

        if isinstance(our_type, intermediate.Enumeration):
            raise AssertionError("Enumeration literals have nothing to verify")

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            shape = f"Shape::{_shape_literal(our_type)}"
            if by_value:
                return cpp_over.generate_call("OneByValue", [expr, shape])

            return cpp_over.generate_call("One", [f"&{expr}", shape])

        elif isinstance(our_type, intermediate.Class):
            return cpp_over.generate_call("Over", [f"*{expr}", "recursive"])

        elif isinstance(our_type, intermediate.NamedUnion):
            return cpp_over.generate_call(
                cpp_over.over_function_name(type_annotation), [expr, "recursive"]
            )

        else:
            assert_never(our_type)

    elif isinstance(
        type_annotation,
        (
            intermediate.ListTypeAnnotation,
            intermediate.SetTypeAnnotation,
            intermediate.TupleTypeAnnotation,
        ),
    ):
        return cpp_over.generate_call(
            cpp_over.over_function_name(type_annotation), [expr, "recursive"]
        )

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
        ),
    ):
        return cpp_over.generate_call(
            "One", [f"&{expr}", f"Shape::{_json_shape_literal(type_annotation)}"]
        )

    elif isinstance(type_annotation, intermediate.JsonObjectTypeAnnotation):
        one = cpp_over.generate_call(
            "One", [f"&{expr}", f"Shape::{_json_shape_literal(type_annotation)}"]
        )

        key_constrained_primitive = intermediate.try_constrained_primitive(
            type_annotation.key
        )
        if key_constrained_primitive is None or (
            id(key_constrained_primitive)
            not in analysis.checked_constrained_primitive_id_set
        ):
            return one

        # NOTE (mristin):
        # We first verify the object itself, which reports if it is not an object
        # at all, and only then its keys.
        each_key = cpp_over.generate_call(
            "EachKey", [expr, f"Shape::{_shape_literal(key_constrained_primitive)}"]
        )
        return cpp_over.generate_call("Chain", [one, each_key])

    else:
        assert_never(type_annotation)

    raise AssertionError("Unexpected execution path")


# fmt: off
@require(
    lambda type_annotation, function_name_set:
    cpp_over.over_function_name(type_annotation) in function_name_set,
    "The function over the type has been collected"
)
@require(
    lambda type_annotation, analysis, function_name_set:
    all(
        cpp_over.over_function_name(called) in function_name_set
        for called in cpp_over.called_function_types(type_annotation, analysis.yields_recursively)
    ),
    "The functions called by the function over the type have been collected"
)
@ensure(
    lambda type_annotation, function_name_set, result:
    cpp_over.called_function_names(
        result[1], defined=cpp_over.over_function_name(type_annotation)
    ).issubset(function_name_set),
    "The function calls only the collected functions"
)
# fmt: on
def _generate_over_function(
    type_annotation: intermediate.TypeAnnotationUnion,
    analysis: _Analysis,
    function_name_set: AbstractSet[str],
) -> Tuple[Optional[Stripped], Stripped]:
    """
    Generate the function over the values of ``type_annotation``.

    For example, we generate for ``List[Name]`` the alias and the function:

    .. code-block:: cpp

        using listOf_Name = std::vector<std::wstring>;

        std::unique_ptr<IIterator> Over_listOf_Name(
          const listOf_Name& value,
          bool recursive
        ) {
          return Each(value, &Over_Name, recursive);
        }

    and for ``Name``, as an item of that list, only the function:

    .. code-block:: cpp

        std::unique_ptr<IIterator> Over_Name(
          const std::wstring& value,
          bool
        ) {
          return One(&value, Shape::kName);
        }

    The ``function_name_set`` contains the names of the collected functions, see
    :py:func:`cpp_over.collect_function_types`.

    Return the alias, if the type needs one, and the function.
    """
    name = cpp_over.over_function_name(type_annotation)

    value_type = cpp_common.generate_type(
        type_annotation=type_annotation,
        types_namespace=cpp_common.TYPES_NAMESPACE,
    )

    body: Stripped

    if isinstance(type_annotation, intermediate.ListTypeAnnotation):
        items = type_annotation.items

        item_function: str
        if isinstance(items, intermediate.OurTypeAnnotation) and isinstance(
            items.our_type, intermediate.Class
        ):
            # NOTE (mristin):
            # The items of a list of instances are shared pointers, which we pass on
            # to the hand-written template.
            interface_name = cpp_naming.interface_name(items.our_type.name)
            item_function = f"ThroughPointer<types::{interface_name}>"
        else:
            item_function = cpp_over.over_function_name(items)

        body = Stripped(
            f"return {cpp_over.generate_call('Each', ['value', f'&{item_function}', 'recursive'])};"
        )

    elif isinstance(type_annotation, intermediate.SetTypeAnnotation):
        # NOTE (mristin):
        # We iterate over the items in the order of the serialization, so that
        # the index in the path of an error matches the serialized array.
        less = cpp_common.generate_set_item_less(type_annotation.items)
        item_function = cpp_over.over_function_name(type_annotation.items)

        body = Stripped(
            f"return {cpp_over.generate_call('EachSorted', ['value', less, f'&{item_function}', 'recursive'])};"
        )

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        components: List[Stripped] = []
        for i, item in enumerate(type_annotation.items):
            item_expression = _generate_over_expression(
                type_annotation=item,
                expr=f"std::get<{i}>(value)",
                by_value=False,
                analysis=analysis,
                function_name_set=function_name_set,
            )
            if item_expression is not None:
                components.append(
                    cpp_over.generate_call("AtIndex", [str(i), item_expression])
                )

        assert len(components) > 0
        if len(components) == 1:
            body = Stripped(f"return {components[0]};")
        else:
            body = Stripped(f"return {cpp_over.generate_call('Chain', components)};")

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation) and isinstance(
        type_annotation.our_type, intermediate.NamedUnion
    ):
        named_union = type_annotation.our_type

        # NOTE (mristin):
        # The alternatives of the variant follow the roots, see
        # :py:func:`cpp_common.generate_named_union_variant_definition`.
        # ``Over`` dispatches dynamically on the instance, so a root with
        # descendants is handled correctly.
        case_blocks = [
            Stripped(
                f"""\
case {i}:
{I}return Over(*common::get<{i}>(value), recursive);"""
            )
            for i in range(len(named_union.roots))
        ]
        case_blocks.append(
            Stripped(
                f"""\
default:
{I}throw std::logic_error("Invalid variant index");"""
            )
        )
        case_blocks_joined = "\n".join(case_blocks)

        body = Stripped(
            f"""\
switch (value.index()) {{
{I}{indent_but_first_line(case_blocks_joined, I)}
}}"""
        )

    else:
        expression = _generate_over_expression(
            type_annotation=type_annotation,
            expr="value",
            by_value=False,
            analysis=analysis,
            function_name_set=function_name_set,
        )
        assert expression is not None
        body = Stripped(f"return {expression};")

    alias: Optional[Stripped] = None

    if isinstance(
        type_annotation,
        (
            intermediate.ListTypeAnnotation,
            intermediate.SetTypeAnnotation,
            intermediate.TupleTypeAnnotation,
        ),
    ):
        alias_name = cpp_over.moniker(type_annotation)
        alias = Stripped(f"using {alias_name} = {value_type};")
        value_type = Stripped(alias_name)

        if not analysis.yields(type_annotation, descend=False):
            # NOTE (mristin):
            # The values can only come from the referenced instances, so we
            # do not iterate at all in the non-recursive mode.
            body = Stripped(
                f"""\
if (!recursive) {{
{I}return Empty();
}}

{body}"""
            )

    function = Stripped(
        f"""\
std::unique_ptr<IIterator> {name}(
{I}const {indent_but_first_line(value_type, I)}& value,
{I}{cpp_over.generate_recursive_parameter(body)}
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )

    return alias, function


# fmt: off
@require(lambda cls, analysis: id(cls) in analysis.yielding_class_id_set)
@require(
    lambda cls, analysis, function_name_set:
    all(
        cpp_over.over_function_name(referenced) in function_name_set
        for prop in cls.properties
        for referenced in cpp_over.referenced_function_types(prop.type_annotation, analysis.yields_recursively)
    ),
    "The functions over the types of the properties have been collected"
)
@ensure(
    lambda cls, function_name_set, result:
    cpp_over.called_function_names(
        result, defined=cpp_over.over_class_function_name(cls)
    ).issubset(function_name_set),
    "The function calls only the collected functions"
)
# fmt: on
def _generate_over_class(
    cls: intermediate.ConcreteClass,
    analysis: _Analysis,
    function_name_set: AbstractSet[str],
) -> Stripped:
    """
    Generate the function over the values of an instance of ``cls``.

    For example, we generate for a class ``Something`` with an invariant and
    a property ``some_names: List[Name]``:

    .. code-block:: cpp

        std::unique_ptr<IIterator> Over_Something(
          const types::ISomething& that,
          bool recursive
        ) {
          return Chain(
            One(&that, Shape::kSomething),
            InProperty(
              iteration::Property::kSomeNames,
              Over_listOf_Name(that.some_names(), recursive)
            )
          );
        }

    The ``function_name_set`` contains the names of the collected functions, see
    :py:func:`cpp_over.collect_function_types`.
    """
    parts: List[Stripped] = []

    if len(cls.invariants) > 0:
        parts.append(
            cpp_over.generate_call("One", ["&that", f"Shape::{_shape_literal(cls)}"])
        )

    for prop in cls.properties:
        # NOTE (mristin):
        # The getters return booleans, integers and floating-point numbers by value,
        # unless they are optional.
        constrained_primitive = (
            intermediate.try_constrained_primitive(prop.type_annotation)
            if isinstance(prop.type_annotation, intermediate.OurTypeAnnotation)
            else None
        )
        by_value = (
            constrained_primitive is not None
            and not cpp_common.primitive_type_is_referencable(
                constrained_primitive.constrainee
            )
        )

        expression = _generate_over_expression(
            type_annotation=prop.type_annotation,
            expr=f"that.{cpp_naming.getter_name(prop.name)}()",
            by_value=by_value,
            analysis=analysis,
            function_name_set=function_name_set,
        )
        if expression is None:
            continue

        property_literal = cpp_naming.enum_literal_name(prop.name)
        parts.append(
            cpp_over.generate_call(
                "InProperty", [f"iteration::Property::{property_literal}", expression]
            )
        )

    assert len(parts) > 0, "Otherwise the class would not have anything to verify"

    body = (
        Stripped(f"return {parts[0]};")
        if len(parts) == 1
        else Stripped(f"return {cpp_over.generate_call('Chain', parts)};")
    )

    interface_name = cpp_naming.interface_name(cls.name)
    name = cpp_over.over_class_function_name(cls)

    return Stripped(
        f"""\
std::unique_ptr<IIterator> {name}(
{I}const types::{interface_name}& that,
{I}{cpp_over.generate_recursive_parameter(body)}
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_over_instance(
    symbol_table: intermediate.SymbolTable, analysis: _Analysis
) -> Stripped:
    """Generate the dispatch over the values of an instance on its runtime type."""
    case_blocks: List[Stripped] = []
    for cls in symbol_table.concrete_classes:
        if id(cls) not in analysis.yielding_class_id_set:
            continue

        model_type_literal = cpp_naming.enum_literal_name(cls.name)
        interface_name = cpp_naming.interface_name(cls.name)

        case_blocks.append(
            Stripped(
                f"""\
case types::ModelType::{model_type_literal}:
{I}return {cpp_over.over_class_function_name(cls)}(
{II}dynamic_cast<const types::{interface_name}&>(instance),
{II}recursive
{I});"""
            )
        )

    doc_comment = Stripped(
        """\
/**
 * Iterate over the values of the \\p instance, dispatched on its runtime type.
 */"""
    )

    if len(case_blocks) == 0:
        return Stripped(
            f"""\
{doc_comment}
std::unique_ptr<IIterator> DispatchOnModelType(
{I}const types::IClass&,
{I}bool
) {{
{I}// NOTE (mristin):
{I}// The instances of no class have anything to verify.
{I}return Empty();
}}"""
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}// NOTE (mristin):
{I}// The instances of the other classes have nothing to verify.
{I}return Empty();"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
{doc_comment}
std::unique_ptr<IIterator> DispatchOnModelType(
{I}const types::IClass& instance,
{I}bool recursive
) {{
{I}switch (instance.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}
}}"""
    )


# endregion Iteration over the values


def _generate_shape_enum(
    symbol_table: intermediate.SymbolTable, uses_json: bool
) -> Stripped:
    """Generate the enumeration of the shapes of the values that we verify."""
    literals = [
        _shape_literal(constrained_primitive)
        for constrained_primitive in symbol_table.constrained_primitives
        if len(constrained_primitive.invariants) > 0
    ]
    literals.extend(
        _shape_literal(cls)
        for cls in symbol_table.concrete_classes
        if len(cls.invariants) > 0
    )
    if uses_json:
        literals.extend(_JSON_SHAPE_LITERALS)

    literals_joined = ",\n".join(
        f"{literal} = {i}" for i, literal in enumerate(literals)
    )

    return Stripped(
        f"""\
/**
 * \\brief Enumerate the shapes of the values that we verify.
 *
 * A shape tells which checks apply to a value, see \\ref ChecksOf.
 */
enum class Shape : std::uint32_t {{
{I}{indent_but_first_line(literals_joined, I)}
}};  // enum class Shape"""
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_checks(
    our_type: Union[intermediate.ConstrainedPrimitive, intermediate.ConcreteClass],
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
) -> Tuple[Optional[Tuple[List[Stripped], Stripped]], Optional[Error]]:
    """
    Generate a check function per invariant of ``our_type``.

    Return the functions, and the case of ``ChecksOf`` for ``our_type``.
    """
    that_definition: Stripped
    if isinstance(our_type, intermediate.ConstrainedPrimitive):
        value_type = cpp_common.generate_primitive_type(our_type.constrainee)
        that_definition = Stripped(
            f"const {value_type}& that = *static_cast<const {value_type}*>(value);"
        )
    else:
        interface_name = cpp_naming.interface_name(our_type.name)
        that_definition = Stripped(
            f"""\
const types::{interface_name}* that = (
{I}static_cast<const types::{interface_name}*>(value)
);"""
        )

    functions: List[Stripped] = []
    checks: List[Stripped] = []
    errors: List[Error] = []

    for i, invariant in enumerate(our_type.invariants):
        condition, error = _transpile_invariant(
            invariant=invariant,
            symbol_table=symbol_table,
            type_inference=type_inference,
        )
        if error is not None:
            errors.append(error)
            continue

        assert condition is not None

        name = f"{cpp_naming.class_name(our_type.name)}_{i}"

        functions.append(
            Stripped(
                f"""\
bool {name}(
{I}const void* value
) {{
{I}{indent_but_first_line(that_definition, I)}
{I}return {indent_but_first_line(condition, I)};
}}"""
            )
        )

        # NOTE (mristin):
        # We need to wrap the description in multiple literals as a single long
        # string literal is often too much for the readability.
        message = "\n".join(
            cpp_common.wstring_literal(line)
            for line in wrap_text_into_lines(invariant.description)
        )

        checks.append(
            Stripped(
                f"""\
{{
{I}&{name},
{I}{indent_but_first_line(message, I)}
}}"""
            )
        )

    if len(errors) > 0:
        return None, Error(
            our_type.parsed.node,
            f"Failed to transpile the invariants of {our_type.name!r}",
            errors,
        )

    checks_joined = ",\n".join(checks)

    case_block = Stripped(
        f"""\
case Shape::{_shape_literal(our_type)}: {{
{I}static const std::vector<Check> checks = {{
{II}{indent_but_first_line(checks_joined, II)}
{I}}};
{I}return checks;
}}"""
    )

    return (functions, case_block), None


def _generate_checks_of(case_blocks: Sequence[Stripped], uses_json: bool) -> Stripped:
    """Generate the function which gives out the checks of a shape."""
    blocks = list(case_blocks)
    no_checks = ""

    if uses_json:
        no_checks = f"{I}static const std::vector<Check> kNoChecks;\n\n"

        json_cases = "\n".join(
            f"case Shape::{literal}:" for literal in _JSON_SHAPE_LITERALS
        )
        blocks.append(
            Stripped(
                f"""\
{json_cases}
{I}// NOTE (mristin):
{I}// The JSON-able values are verified by the nested verification.
{I}return kNoChecks;"""
            )
        )

    blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::logic_error(
{II}common::Concat(
{III}"Unexpected shape: ",
{III}std::to_string(static_cast<std::uint32_t>(shape))
{II})
{I});"""
        )
    )

    blocks_joined = "\n".join(blocks)

    return Stripped(
        f"""\
/**
 * Give out the checks of the values of the \\p shape.
 */
const std::vector<Check>& ChecksOf(Shape shape) {{
{no_checks}\
{I}switch (shape) {{
{II}{indent_but_first_line(blocks_joined, II)}
{I}}}
}}"""
    )


def _generate_new_nested_verificator(uses_json: bool) -> Stripped:
    """Generate the factory of the nested verifications of the values."""
    doc_comment = Stripped(
        """\
/**
 * \\brief Create the nested verification of the \\p value, if its \\p shape has one.
 *
 * \\return nullptr if the shape has no nested verification
 */"""
    )

    if not uses_json:
        return Stripped(
            f"""\
{doc_comment}
std::unique_ptr<impl::IVerificator> NewNestedVerificator(
{I}Shape,
{I}const void*
) {{
{I}// NOTE (mristin):
{I}// The meta-model uses no JSON-able values, so no value needs a nested
{I}// verification.
{I}return nullptr;
}}"""
        )

    case_blocks: List[Stripped] = []
    for literal, json_value_shape in zip(
        _JSON_SHAPE_LITERALS, ("kAny", "kArray", "kObject"), strict=True
    ):
        case_blocks.append(
            Stripped(
                f"""\
case Shape::{literal}:
{I}return common::make_unique<JsonValueVerificator>(
{II}*static_cast<const nlohmann::json*>(value),
{II}JsonValueShape::{json_value_shape}
{I});"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}return nullptr;"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
{doc_comment}
std::unique_ptr<impl::IVerificator> NewNestedVerificator(
{I}Shape shape,
{I}const void* value
) {{
{I}switch (shape) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}
}}"""
    )


def _generate_implementation_of_verify_constrained_primitive(
    constrained_primitive: intermediate.ConstrainedPrimitive,
) -> Stripped:
    """Generate the implementation of the function ``Verify{Constrained Primitive}``."""
    verify_name = cpp_naming.function_name(
        Identifier(f"verify_{constrained_primitive.name}")
    )

    value_type = cpp_common.generate_primitive_type_with_const_ref_if_applicable(
        primitive_type=constrained_primitive.constrainee
    )

    if len(constrained_primitive.invariants) == 0:
        return Stripped(
            f"""\
std::unique_ptr<IVerification> {verify_name}(
{I}{value_type}
) {{
{I}// NOTE (mristin):
{I}// There are no invariants to verify.
{I}return common::make_unique<ValuesVerification>(Empty());
}}"""
        )

    shape = f"Shape::{_shape_literal(constrained_primitive)}"

    values = (
        cpp_over.generate_call("One", ["&that", shape])
        if cpp_common.primitive_type_is_referencable(constrained_primitive.constrainee)
        else cpp_over.generate_call("OneByValue", ["that", shape])
    )

    return Stripped(
        f"""\
std::unique_ptr<IVerification> {verify_name}(
{I}{value_type} that
) {{
{I}return common::make_unique<ValuesVerification>(
{II}{indent_but_first_line(values, II)}
{I});
}}"""
    )


def _generate_non_recursive_verification() -> List[Stripped]:
    """Generate the ``NonRecursiveVerification`` class."""
    return [
        Stripped("// region NonRecursiveVerification"),
        Stripped(
            f"""\
NonRecursiveVerification::NonRecursiveVerification(
{I}const std::shared_ptr<types::IClass>& instance
) : instance_(instance) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Iterator NonRecursiveVerification::begin() const {{
{I}return IterateErrors(DispatchOnModelType(*instance_, false));
}}"""
        ),
        Stripped(
            f"""\
const Iterator& NonRecursiveVerification::end() const {{
{I}return PastLastError();
}}"""
        ),
        Stripped("// endregion NonRecursiveVerification"),
    ]


def _generate_recursive_verification() -> List[Stripped]:
    """Generate the ``RecursiveVerification`` class."""
    return [
        Stripped("// region RecursiveVerification"),
        Stripped(
            f"""\
RecursiveVerification::RecursiveVerification(
{I}const std::shared_ptr<types::IClass>& instance
) : instance_(instance) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Iterator RecursiveVerification::begin() const {{
{I}return IterateErrors(DispatchOnModelType(*instance_, true));
}}"""
        ),
        Stripped(
            f"""\
const Iterator& RecursiveVerification::end() const {{
{I}return PastLastError();
}}"""
        ),
        Stripped("// endregion RecursiveVerification"),
    ]


def _is_used(function: str, code: str) -> bool:
    """Check whether the ``function`` is called in the generated ``code``."""
    return re.search(rf"\b{function}(\(|<)", code) is not None


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable,
    type_inference: intermediate_type_inference.TypeInference,
    spec_impls: specific_implementations.SpecificImplementations,
    library_namespace: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate implementation of verification logic."""
    namespace = Stripped(f"{library_namespace}::{cpp_common.VERIFICATION_NAMESPACE}")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    errors: List[Error] = []

    uses_json = intermediate_uses.json_types(symbol_table)

    json_value_verification_include = (
        '#include "json_value_verification.hpp"\n\n' if uses_json else ""
    )

    # NOTE (mristin):
    # We transpile ``abs`` to ``std::abs``. Its overloads for the integers live in
    # ``<cstdlib>``, while its overloads for the floating-point numbers live in
    # ``<cmath>``.
    std_includes = ["<map>", "<set>", "<vector>"]
    if intermediate_uses.abs_call(symbol_table):
        std_includes.extend(["<cmath>", "<cstdlib>"])

    # NOTE (mristin):
    # The failed assertions throw ``std::logic_error``.
    if intermediate_uses.assert_statements_in(symbol_table.verification_functions):
        std_includes.append("<stdexcept>")

    std_includes_joined = "\n".join(
        f"#include {std_include}" for std_include in sorted(std_includes)
    )

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            f"""\
{json_value_verification_include}\
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/constants.hpp"
#include "{include_prefix_path}/pattern.hpp"
#include "{include_prefix_path}/revm.hpp"
#include "{include_prefix_path}/stringification.hpp"
#include "{include_prefix_path}/verification.hpp"

#pragma warning(push, 0)
{std_includes_joined}
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(namespace),
        *_generate_error_implementation(),
    ]

    # NOTE (mristin):
    # The internal verification functions live in the anonymous namespace, so that
    # they are invisible outside this translation unit. We declare them upfront so
    # that the other verification functions and the checks can call them regardless
    # of the order of the definitions.
    internal_verifications = [
        verification
        for verification in symbol_table.verification_functions
        if verification.visibility is intermediate.Visibility.INTERNAL
    ]

    if len(internal_verifications) > 0:
        blocks.append(
            Stripped("// region Declarations of internal verification functions")
        )
        blocks.append(Stripped("namespace {"))

        for verification in internal_verifications:
            block, error = _generate_verification_function_definition(
                verification=verification, spec_impls=spec_impls
            )
            if error is not None:
                errors.append(error)
            else:
                assert block is not None
                blocks.append(block)

        blocks.append(Stripped("}  // namespace"))
        blocks.append(
            Stripped("// endregion Declarations of internal verification functions")
        )

    if len(symbol_table.verification_functions) > 0:
        blocks.append(Stripped("// region Verification functions"))

        for verification in symbol_table.verification_functions:
            # NOTE (mristin):
            # The implementation-specific snippet can be empty, *e.g.*, if
            # the function is templated and defined in the header snippet.
            definition: Optional[Stripped] = None

            if isinstance(verification, intermediate.PatternVerification):
                definition = _generate_pattern_verification_implementation(
                    verification=verification
                )

            elif isinstance(verification, intermediate.TranspilableVerification):
                # NOTE (mristin):
                # The public generic verification functions are templates defined
                # in the header, see :py:func:`generate_header`.
                if (
                    _is_generic(verification)
                    and verification.visibility is intermediate.Visibility.PUBLIC
                ):
                    continue

                block, error = _generate_implementation_of_transpilable_verification(
                    verification=verification,
                    symbol_table=symbol_table,
                    type_inference=type_inference,
                )

                if error is not None:
                    errors.append(error)
                else:
                    assert block is not None
                    definition = block

            elif isinstance(
                verification, intermediate.ImplementationSpecificVerification
            ):
                implementation_key = specific_implementations.ImplementationKey(
                    f"verification/{verification.name}.cpp"
                )

                block = spec_impls.get(implementation_key, None)

                if block is None:
                    errors.append(
                        Error(
                            verification.parsed.node,
                            f"The implementation is missing for "
                            f"the implementation-specific verification "
                            f"function: {implementation_key}",
                        )
                    )
                else:
                    # NOTE (mristin):
                    # Some verification functions only live in the header and have
                    # no code in the implementation file. For example, the verification
                    # functions which are templated.
                    if len(block.strip()) > 0:
                        definition = block
            else:
                assert_never(verification)

            if definition is None:
                continue

            if verification.visibility is intermediate.Visibility.INTERNAL:
                blocks.append(
                    Stripped(
                        f"""\
namespace {{
{definition}
}}  // namespace"""
                    )
                )
            else:
                blocks.append(definition)

        blocks.append(Stripped("// endregion Verification functions"))

    # region Checks

    constrained_primitives_and_classes: List[
        Union[intermediate.ConstrainedPrimitive, intermediate.ConcreteClass]
    ] = [
        *symbol_table.constrained_primitives,
        *symbol_table.concrete_classes,
    ]

    if uses_json:
        taken_literal_set = {
            _shape_literal(our_type) for our_type in constrained_primitives_and_classes
        }
        for literal in _JSON_SHAPE_LITERALS:
            if literal in taken_literal_set:
                errors.append(
                    Error(
                        None,
                        f"The shape literal {literal!r} of JSON-able values clashes "
                        f"with a class or a constrained primitive of the same name. "
                        f"Please rename it, or contact the developers.",
                    )
                )

    check_functions: List[Stripped] = []
    checks_of_case_blocks: List[Stripped] = []

    for our_type in constrained_primitives_and_classes:
        if len(our_type.invariants) == 0:
            continue

        checks, error = _generate_checks(
            our_type=our_type,
            symbol_table=symbol_table,
            type_inference=type_inference,
        )
        if error is not None:
            errors.append(error)
            continue

        assert checks is not None
        functions, case_block = checks
        check_functions.extend(functions)
        checks_of_case_blocks.append(case_block)

    # endregion Checks

    # region Iteration over the values

    analysis = _Analysis(symbol_table=symbol_table)

    # NOTE (mristin):
    # We first collect the lists, tuples and named unions which need a function,
    # and only then generate the functions, so that the generation itself has no
    # state to keep.
    function_types, collection_errors = cpp_over.collect_function_types(
        classes=[
            cls
            for cls in symbol_table.concrete_classes
            if id(cls) in analysis.yielding_class_id_set
        ],
        yields=analysis.yields_recursively,
    )

    generated_over: List[Stripped] = []

    if collection_errors is not None:
        errors.extend(collection_errors)
    else:
        assert function_types is not None

        function_name_set = frozenset(
            cpp_over.over_function_name(function_type)
            for function_type in function_types
        )

        aliases_and_functions = [
            _generate_over_function(
                type_annotation=function_type,
                analysis=analysis,
                function_name_set=function_name_set,
            )
            for function_type in function_types
        ]

        generated_over.extend(
            alias for alias, _ in aliases_and_functions if alias is not None
        )
        generated_over.extend(function for _, function in aliases_and_functions)

        generated_over.extend(
            _generate_over_class(
                cls=cls, analysis=analysis, function_name_set=function_name_set
            )
            for cls in symbol_table.concrete_classes
            if id(cls) in analysis.yielding_class_id_set
        )

        generated_over.append(
            _generate_over_instance(symbol_table=symbol_table, analysis=analysis)
        )

    verify_constrained_primitives = [
        _generate_implementation_of_verify_constrained_primitive(
            constrained_primitive=constrained_primitive
        )
        for constrained_primitive in symbol_table.constrained_primitives
    ]

    generated_code = "\n".join([*generated_over, *verify_constrained_primitives])

    combinators = [*_EMPTY]
    for function, combinator in (
        ("One", _ONE),
        ("OneByValue", _ONE_BY_VALUE),
        ("Chain", _CHAIN),
        ("InProperty", _IN_PROPERTY),
        ("AtIndex", _AT_INDEX),
        ("Each", _EACH),
        ("EachSorted", _EACH_SORTED),
        ("Over", _OVER),
        ("ThroughPointer", _OVER),
        ("EachKey", _EACH_KEY),
    ):
        if _is_used(function, generated_code) and combinator[0] not in combinators:
            combinators.extend(combinator)

    # endregion Iteration over the values

    blocks.extend(
        [
            Stripped("namespace {"),
            _generate_shape_enum(symbol_table=symbol_table, uses_json=uses_json),
            *_CHECK_STRUCT,
            Stripped("// region Checks"),
            *check_functions,
            _generate_checks_of(case_blocks=checks_of_case_blocks, uses_json=uses_json),
            Stripped("// endregion Checks"),
            _generate_new_nested_verificator(uses_json=uses_json),
            Stripped("// region Iteration over the values"),
            *_IITERATOR,
            *combinators,
            *generated_over,
            Stripped("// endregion Iteration over the values"),
            Stripped("// region Iteration over the errors"),
            *_ERROR_ITERATOR,
        ]
    )

    if len(symbol_table.constrained_primitives) > 0:
        blocks.extend(_VALUES_VERIFICATION)

    blocks.extend(
        [
            Stripped("// endregion Iteration over the errors"),
            Stripped("}  // namespace"),
        ]
    )

    if len(symbol_table.constrained_primitives) > 0:
        blocks.append(Stripped("// region Verification of constrained primitives"))
        blocks.extend(verify_constrained_primitives)
        blocks.append(Stripped("// endregion Verification of constrained primitives"))

    blocks.extend(
        [
            *_generate_non_recursive_verification(),
            *_generate_recursive_verification(),
            *_generate_iterator_implementation(),
        ]
    )

    if len(errors) > 0:
        return None, errors

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

    return writer.getvalue(), None


assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
