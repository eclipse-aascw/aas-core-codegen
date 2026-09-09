"""Generate code of functions to iterate over instances."""

import io
from typing import (
    Optional,
    Dict,
    List,
    Tuple,
    Sequence,
    Set,
    Final,
    FrozenSet,
)

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import (
    Error,
    Identifier,
    assert_never,
    Stripped,
    indent_but_first_line,
)
from aas_core_codegen.cpp import (
    common as cpp_common,
    naming as cpp_naming,
    yielding as cpp_yielding,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)
from aas_core_codegen.intermediate import construction as intermediate_construction
from aas_core_codegen.yielding import flow as yielding_flow


# region Check


@ensure(lambda result: not (result is not None) or (len(result) >= 1))
def _verify_that_property_enum_literals_do_not_collide(
    symbol_table: intermediate.SymbolTable,
) -> Optional[List[Error]]:
    """Check that the literal names for the properties do not collied within a class."""
    errors = []  # type: List[Error]

    # NOTE (mristin):
    # We use getter name as string representation for the enum ``Property``, so we have
    # to make sure that there are no conflicts.
    literal_name_to_getter_and_prop = (
        dict()
    )  # type: Dict[str, Tuple[str, intermediate.Property]]

    for cls in symbol_table.classes:
        observed_literal_names = dict()  # type: Dict[str, str]
        for prop in cls.properties:
            literal_name = cpp_naming.enum_literal_name(prop.name)

            conflicting_property_name = observed_literal_names.get(literal_name, None)

            if conflicting_property_name is not None:
                errors.append(
                    Error(
                        cls.parsed.node,
                        f"The property {prop.name!r} and "
                        f"the property {conflicting_property_name!r} conflict in "
                        f"the C++ Property literal name {literal_name!r} "
                        f"in class {cls.name!r}",
                    )
                )
                continue

            getter = cpp_naming.getter_name(prop.name)

            another_getter_and_prop = literal_name_to_getter_and_prop.get(
                literal_name, None
            )
            if another_getter_and_prop is not None:
                another_getter, another_prop = another_getter_and_prop

                if another_getter != getter:
                    errors.append(
                        Error(
                            cls.parsed.node,
                            f"The property {prop.name!r} from class {cls.name!r} and "
                            f"the property {another_prop.name!r} "
                            f"from class {another_prop.specified_for.name!r} "
                            f"have differing getter names, "
                            f"{getter!r} and {another_getter!r}, respectively, "
                            f"for the literal in C++ enum Property {literal_name!r}",
                        )
                    )
                    continue
            else:
                literal_name_to_getter_and_prop[literal_name] = (getter, prop)

            observed_literal_names[literal_name] = prop.name

    if len(errors) > 0:
        return errors

    return None


# endregion

# region Generation


def _generate_property_enum(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the enum which represents all the properties of all the classes."""
    literal_name_set = set()  # type: Set[Identifier]
    for cls in symbol_table.classes:
        for prop in cls.properties:
            literal_name_set.add(cpp_naming.enum_literal_name(prop.name))

    literal_names = sorted(literal_name_set)

    literal_definitions = [
        f"{literal_name} = {i}" for i, literal_name in enumerate(literal_names)
    ]

    literal_definitions_joined = ",\n".join(literal_definitions)

    property_enum = cpp_naming.enum_name(Identifier("Property"))

    return Stripped(
        f"""\
/**
 * Define the properties over all the classes to compactly represent the paths.
 */
enum class {property_enum} : std::uint32_t {{
{I}{indent_but_first_line(literal_definitions_joined, I)}
}};"""
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
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate header of functions to iterate over instances."""
    collision_errors = _verify_that_property_enum_literals_do_not_collide(
        symbol_table=symbol_table
    )
    if collision_errors is not None:
        return None, collision_errors

    namespace = Stripped(f"{library_namespace}::iteration")

    include_guard_var = cpp_common.include_guard_var(namespace)

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    property_enum = cpp_naming.enum_name(Identifier("Property"))
    property_to_wstring = cpp_naming.function_name(Identifier("property_to_wstring"))

    blocks = [
        Stripped(
            f"""\
#ifndef {include_guard_var}
#define {include_guard_var}"""
        ),
        cpp_common.WARNING,
        Stripped(
            f"""\
#include "{include_prefix_path}/types.hpp"

#pragma warning(push, 0)
#include <deque>
#include <iterator>
#include <memory>
#include <string>
#pragma warning(pop)"""
        ),
        cpp_common.generate_namespace_opening(library_namespace),
        Stripped(
            """\
/**
 * \\defgroup iteration Define functions and structures to iterate over instances.
 * @{
*/
namespace iteration {"""
        ),
        Stripped("// region Pathing"),
        _generate_property_enum(symbol_table=symbol_table),
        Stripped(
            f"""\
std::wstring {property_to_wstring}(
{I}{property_enum} property
);"""
        ),
        Stripped(
            f"""\
/**
 * Represent a segment of a path to some value.
 */
class ISegment {{
 public:
{I}virtual std::wstring ToWstring() const = 0;
{I}virtual std::unique_ptr<ISegment> Clone() const = 0;
{I}virtual ~ISegment() = default;
}};  // class ISegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent a property access on a path.
 */
struct PropertySegment : public ISegment {{
{I}/**
{I} * Enumeration of the property
{I} */
{I}Property property;

{I}PropertySegment(
{II}Property a_property
{I});

{I}std::wstring ToWstring() const override;
{I}std::unique_ptr<ISegment> Clone() const override;

{I}~PropertySegment() override = default;
}};  // struct PropertySegment"""
        ),
        Stripped(
            f"""\
/**
 * Represent an index access on a path.
 */
struct IndexSegment : public ISegment {{
{I}/**
{I} * Index of the item
{I} */
{I}size_t index;

{I}explicit IndexSegment(
{II}size_t an_index
{I});

{I}std::wstring ToWstring() const override;
{I}std::unique_ptr<ISegment> Clone() const override;

{I}~IndexSegment() override = default;
}};  // struct IndexSegment"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Represent a path to some value.
 *
 * This is a path akin to C++ expressions. It is not to be confused with different
 * paths used in the specification. This path class is meant to help with reporting.
 * For example, we can use this path to let the user know when there is
 * a verification error in a model which can concern instances, but also properties
 * and items in the lists.
 */
struct Path {{
{I}// NOTE (mristin):
{I}// We did not implement the reflection at the moment since we did not have a use
{I}// case for it. If you need reflection, please contact the developers. It should
{I}// be a small step going from paths to dereferencing to getters and setters.

{I}std::deque<std::unique_ptr<ISegment> > segments;

{I}Path();
{I}Path(const Path& other);
{I}Path(Path&& other);
{I}Path& operator=(const Path& other);
{I}Path& operator=(Path&& other);

{I}std::wstring ToWstring() const;
}};  // struct Path"""
        ),
        Stripped("// endregion Pathing"),
        Stripped("// region Iterators and descent"),
        Stripped(
            f"""\
/// \\cond HIDDEN
namespace impl {{
class IIterator {{
 public:
{I}virtual void Start() = 0;
{I}virtual void Next() = 0;
{I}virtual bool Done() const = 0;
{I}virtual const std::shared_ptr<types::IClass>& Get() const = 0;
{I}virtual long Index() const = 0;

{I}/// Prepend the segments to the path reflecting where this iterator points to.
{I}virtual void PrependToPath(Path* path) const = 0;

{I}virtual std::unique_ptr<IIterator> Clone() const = 0;

{I}virtual ~IIterator() = default;
}};  // class IIterator
}}  // namespace impl
/// \\endcond"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Iterate over an AAS instance.
 *
 * Unlike STL, this is <em>not</em> a light-weight iterator. We implement
 * a "yielding" iterator by leveraging code generation so that we always keep
 * the model stack as well as the properties iterated thus far.
 *
 * This means that copy-construction and equality comparisons are much more heavy-weight
 * than you'd usually expect from an STL iterator. For example, if you want to sort
 * model instances, you are most probably faster if you populate a vector, and then
 * sort the vector.
 *
 * Also, given that this iterator is not light-weight, you should in almost all cases
 * avoid the postfix increment (it++) and prefer the prefix one (++it) as the postfix
 * increment would create an iterator copy every time.
 *
 * The value of the iterator is intentionally constant reference to a shared pointer.
 * This merely means that you can not change the <em>pointer</em> while you are
 * iterating. The pointed instances, however, is freely mutable. This way you can make
 * further shared pointers, or include the pointed instances in other collections
 * different from the original container. On the other hand, the normal case, where
 * the pointer is only de-referenced, remains efficient as no copy of
 * the shared pointer is created.
 *
 * We follow the C++ standard, and assume that comparison between the two iterators
 * over two different instances results in undefined behavior. See
 * http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2009/n2948.html and
 * https://stackoverflow.com/questions/4657513/comparing-iterators-from-different-containers.
 *
 * Since we use const references to shared pointers here you can also share ownership
 * over instances in your own external containers. Making a copy of a shared pointer
 * will automatically increase reference count, even though there is a constant
 * reference. Since we do not make copies of the shared pointers, it is very important
 * that the given shared pointers outlive the iteration, lest cause undefined behavior.
 *
 * Changing the references <em>during</em> the iteration invalidates the iterators and
 * results in undefined behavior. This is similar to many of the containers in the STL,
 * see: https://stackoverflow.com/questions/6438086/iterator-invalidation-rules-for-c-containers
 *
 * See these StackOverflow questions for performance related to shared pointers and
 * constant references to shared pointers (copying <em>versus</em> referencing):
 * * https://stackoverflow.com/questions/12002480/passing-stdshared-ptr-to-constructors/12002668#12002668
 * * https://stackoverflow.com/questions/3310737/should-we-pass-a-shared-ptr-by-reference-or-by-value
 * * https://stackoverflow.com/questions/37610494/passing-const-shared-ptrt-versus-just-shared-ptrt-as-parameter
 *
 * The following StackOverflow question and answers go into more detail how const-ness
 * and shared pointers fit together:
 * https://stackoverflow.com/questions/36271663/why-does-copying-a-const-shared-ptr-not-violate-const-ness
 */
class Iterator {{
{I}using iterator_category = std::forward_iterator_tag;
{I}/// The difference is meaningless, but has to be defined.
{I}using difference_type = std::ptrdiff_t;
{I}using value_type = std::shared_ptr<types::IClass>;
{I}using pointer = const std::shared_ptr<types::IClass>*;
{I}using reference = const std::shared_ptr<types::IClass>&;

 public:
{I}Iterator(const Iterator& other);
{I}Iterator(Iterator&& other);

{I}Iterator& operator=(const Iterator& other);
{I}Iterator& operator=(Iterator&& other);

{I}reference operator*() const;
{I}pointer operator->();

{I}// Prefix increment
{I}Iterator& operator++();

{I}// Postfix increment
{I}Iterator operator++(int);

{I}friend bool operator==(const Iterator& a, const Iterator& b);
{I}friend bool operator!=(const Iterator& a, const Iterator& b);

{I}friend class Descent;
{I}friend class DescentOnce;
{I}friend Path MaterializePath(const Iterator& iterator);
{I}friend void PrependToPath(const Iterator& iterator, Path* path);

 private:
{I}explicit Iterator(
{II}std::unique_ptr<impl::IIterator> implementation
{I}) :
{II}implementation_(std::move(implementation)) {{
{II}  // Intentionally empty.
{I}}}

{I}std::unique_ptr<impl::IIterator> implementation_;
}};"""
        ),
        Stripped("bool operator==(const Iterator& a, const Iterator& b);"),
        Stripped("bool operator!=(const Iterator& a, const Iterator& b);"),
        Stripped(
            """\
/**
 * \\brief Materialize the path that the \\p iterator points to.
 *
 * We assume that you always want a copy of the path, rather than inspect
 * the path during the iteration.
 *
 * \\param iterator for which we want to materialize the path
 * \\return Path referring to the pointed instance
 */
Path MaterializePath(const Iterator& iterator);"""
        ),
        Stripped(
            f"""\
/**
 * Build a facade over an instance to iterate over instances referenced from it.
 */
class IDescent {{
 public:
{I}virtual Iterator begin() const = 0;
{I}virtual const Iterator& end() const = 0;
{I}virtual ~IDescent() = default;
}};  // class IDescent"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Provide a recursive iterable over all the instances referenced from
 * an instance.
 *
 * Please see the notes in the class Iterator regarding the constant reference to
 * a shared pointer. In short, the instance should outlive the descent, so make
 * sure you do not destroy it during the descent.
 *
 * Range-based loops should fit the vast majority of the use cases:
 * \\code
 * std::shared_ptr<types::Environment> env = ...;
 * for (
 * {I}const std::shared_ptr<types::IClass>& instance
 * {I}: Descent(env)
 * ) {{
 * {I}do_something(instance);
 * }}
 * \\endcode
 *
 * \\param that instance to be iterated over recursively
 * \\return Iterable over referenced instances
 */
class Descent : public IDescent {{
 public:
{I}Descent(
{II}std::shared_ptr<types::IClass> instance
{I});

{I}Iterator begin() const override;
{I}const Iterator& end() const override;

{I}~Descent() override = default;

 private:
{I}std::shared_ptr<types::IClass> instance_;
}};  // class Descent"""
        ),
        Stripped(
            f"""\
/**
 * \\brief Provide a non-recursive iterable over the instances referenced from
 * an instance.
 *
 * Please see the notes in the class Iterator regarding the constant reference to
 * a shared pointer. In short, the instance should outlive the descent, so make
 * sure you do not destroy it during the descent.
 *
 * Range-based loops should fit the vast majority of the use cases:
 * \\code
 * std::shared_ptr<types::Environment> env = ...;
 * for (
 * {I}const std::shared_ptr<types::IClass>& instance
 * {I}: DescentOnce(env)
 * ) {{
 * {I}do_something(instance);
 * }}
 * \\endcode
 */
class DescentOnce : public IDescent {{
 public:
{I}DescentOnce(
{II}std::shared_ptr<types::IClass> instance
{I});

{I}Iterator begin() const override;
{I}const Iterator& end() const override;

{I}~DescentOnce() override = default;

 private:
{I}std::shared_ptr<types::IClass> instance_;
}};  // class DescentOnce"""
        ),
        Stripped("// endregion Iterators and descent"),
    ]  # type: List[Stripped]

    if len(symbol_table.enumerations) > 0:
        blocks.append(Stripped("// region Over enumerations"))

        for enum in symbol_table.enumerations:
            enum_name = cpp_naming.enum_name(enum.name)
            over_enum = cpp_naming.constant_name(Identifier(f"over_{enum.name}"))

            blocks.append(
                Stripped(
                    f"""\
/**
 * \\brief Give a container for all the literals of types::{enum_name}.
 *
 * This container is practical when you want to show the literals in a GUI or a CLI.
 */
extern const std::vector<types::{enum_name}> {over_enum};"""
                )
            )

        blocks.append(Stripped("// endregion Over enumerations"))

    blocks.extend(
        [
            Stripped(
                """\
}  // namespace iteration
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


def _generate_property_to_wstring_implementation(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the implementation of the stringification for ``Property`` enum."""
    literal_name_to_getter = dict()  # type: Dict[Identifier, Identifier]
    literal_name_set = set()  # type: Set[Identifier]

    for cls in symbol_table.classes:
        for prop in cls.properties:
            literal_name = cpp_naming.enum_literal_name(prop.name)
            literal_name_to_getter[literal_name] = cpp_naming.getter_name(prop.name)

            literal_name_set.add(literal_name)

    literal_names = sorted(literal_name_set)

    property_enum = cpp_naming.enum_name(Identifier("Property"))

    case_blocks = []  # type: List[Stripped]
    for literal_name in literal_names:
        getter = literal_name_to_getter[literal_name]

        case_blocks.append(
            Stripped(
                f"""\
case {property_enum}::{literal_name}:
{I}return {cpp_common.wstring_literal(getter)};"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}throw std::invalid_argument(
{II}common::Concat(
{III}"Unexpected property literal: ",
{III}std::to_string(
{IIII}static_cast<std::uint32_t>(property)
{III})
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    property_to_wstring = cpp_naming.function_name(Identifier("property_to_wstring"))

    return Stripped(
        f"""\
/**
 * Translate the enumeration literal \\p property to text.
 *
 * \\param property to be converted into text
 * \\return text representation of \\p property
 * \\throw std::invalid_argument if \\p property invalid
 */
std::wstring {property_to_wstring}(
{I}Property property
) {{
{I}switch (property) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}
}}  // function to_wstring"""
    )


def _generate_property_segment_implementation() -> List[Stripped]:
    """Generate the implementation of ``PropertySegment`` struct."""
    property_to_wstring = cpp_naming.function_name(Identifier("property_to_wstring"))

    return [
        Stripped("// region struct PropertySegment"),
        Stripped(
            f"""\
PropertySegment::PropertySegment(Property a_property) {{
{I}property = a_property;
}}"""
        ),
        Stripped(
            f"""\
std::wstring PropertySegment::ToWstring() const {{
{I}return common::Concat(
{II}L".",
{II}{property_to_wstring}(property)
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> PropertySegment::Clone() const {{
{I}return common::make_unique<PropertySegment>(*this);
}}"""
        ),
        Stripped("// endregion struct PropertySegment"),
    ]


def _generate_index_segment_implementation() -> List[Stripped]:
    """Generate the implementation of ``IndexSegment`` struct."""
    return [
        Stripped("// region struct IndexSegment"),
        Stripped(
            f"""\
IndexSegment::IndexSegment(size_t an_index) {{
{I}index = an_index;
}}"""
        ),
        Stripped(
            f"""\
std::wstring IndexSegment::ToWstring() const {{
{I}return common::Concat(
{II}L"[",
{II}std::to_wstring(index),
{II}L"]"
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> IndexSegment::Clone() const {{
{I}return common::make_unique<IndexSegment>(*this);
}}"""
        ),
        Stripped("// endregion struct IndexSegment"),
    ]


def _generate_path_implementation() -> List[Stripped]:
    """Generate the implementation of the ``Path`` struct."""
    return [
        Stripped("// region struct Path"),
        Stripped(
            f"""\
Path::Path() {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Path::Path(const Path& other) {{
{I}for (const std::unique_ptr<ISegment>& segment : other.segments) {{
{II}segments.emplace_back(segment->Clone());
{I}}}
}}"""
        ),
        Stripped(
            f"""\
Path::Path(Path&& other) {{
{I}segments = std::move(other.segments);
}}"""
        ),
        Stripped(
            f"""\
Path& Path::operator=(const Path& other) {{
{I}segments.clear();
{I}for (const std::unique_ptr<ISegment>& segment : other.segments) {{
{II}segments.emplace_back(segment->Clone());
{I}}}
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
Path& Path::operator=(Path&& other) {{
{I}if (this != &other) {{
{II}segments = std::move(other.segments);
{I}}}
{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
std::wstring Path::ToWstring() const {{
{I}std::vector<std::wstring> parts;
{I}parts.reserve(segments.size());

{I}for (const std::unique_ptr<ISegment>& segment : segments ) {{
{II}parts.emplace_back(segment->ToWstring());
{I}}}

{I}size_t size = 0;
{I}for (const std::wstring& part : parts) {{
{II}size += part.size();
{I}}}

{I}std::wstring result;
{I}result.reserve(size);
{I}for (const std::wstring& part : parts) {{
{II}result.append(part);
{I}}}

{I}return result;
}}"""
        ),
        Stripped("// endregion struct Path"),
    ]


class IteratorQualities:
    """Query the qualities of a non-recursive iterator corresponding to a class."""

    #: The class corresponding to the iterator
    cls: Final[intermediate.ConcreteClass]

    #: The properties which should be iterated over
    relevant_properties: Final[Sequence[intermediate.Property]]

    #: A set of Python IDs of the relevant properties
    relevant_property_id_set: Final[FrozenSet[int]]

    #: Set if the class contains a property which is a list of instances
    cls_contains_a_list_or_tuple_property: Final[bool]

    def __init__(self, cls: intermediate.ConcreteClass) -> None:
        """Initialize with the given class."""
        relevant_properties = []  # type: List[intermediate.Property]

        cls_contains_a_list_or_tuple_property = False

        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
                pass

            elif isinstance(type_anno, intermediate.OurTypeAnnotation):
                if isinstance(type_anno.our_type, intermediate.Enumeration):
                    pass

                elif isinstance(type_anno.our_type, intermediate.ConstrainedPrimitive):
                    pass

                elif isinstance(
                    type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    relevant_properties.append(prop)

                else:
                    assert_never(type_anno.our_type)

            elif isinstance(type_anno, intermediate.ListTypeAnnotation):
                if isinstance(type_anno.items, intermediate.PrimitiveTypeAnnotation):
                    pass

                elif isinstance(type_anno.items, intermediate.OurTypeAnnotation):
                    if isinstance(type_anno.items.our_type, intermediate.Enumeration):
                        pass

                    elif isinstance(
                        type_anno.items.our_type, intermediate.ConstrainedPrimitive
                    ):
                        pass

                    elif isinstance(
                        type_anno.items.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        cls_contains_a_list_or_tuple_property = True

                        relevant_properties.append(prop)

                    else:
                        assert_never(type_anno.items.our_type)

                else:
                    raise NotImplementedError(
                        f"NOTE (mristin): We expect only lists of atomic values "
                        f"at the moment, but you specified {prop.type_annotation} "
                        f"in class {cls.name!r} and property {prop.name!r}. "
                        f"Please contact the developers if you need this feature."
                    )

            elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                contains_a_class = False
                for item_type_anno in type_anno.items:
                    assert isinstance(
                        item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                    ), (
                        "Tuple items are restricted to atomic types (primitives, "
                        "constrained primitives, classes and enumerations) by "
                        "intermediate._translate._verify_only_simple_type_patterns, "
                        "so no nested optionals, lists or tuples are expected here."
                    )

                    if isinstance(
                        item_type_anno, intermediate.OurTypeAnnotation
                    ) and isinstance(
                        item_type_anno.our_type,
                        (intermediate.AbstractClass, intermediate.ConcreteClass),
                    ):
                        contains_a_class = True

                if contains_a_class:
                    cls_contains_a_list_or_tuple_property = True
                    relevant_properties.append(prop)

            else:
                assert_never(type_anno)

        self.cls = cls
        self.relevant_properties = relevant_properties
        self.relevant_property_id_set = frozenset(
            id(prop) for prop in self.relevant_properties
        )
        self.cls_contains_a_list_or_tuple_property = (
            cls_contains_a_list_or_tuple_property
        )


@require(lambda iterator_qualities: len(iterator_qualities.relevant_properties) == 0)
def _generate_empty_iterator_over_cls(
    iterator_qualities: IteratorQualities,
) -> List[Stripped]:
    """Generate the iterator over a class with no references to other instances."""
    interface_name = cpp_naming.interface_name(iterator_qualities.cls.name)
    iterator_over_cls = cpp_naming.class_name(
        Identifier(f"Iterator_over_{iterator_qualities.cls.name}")
    )

    return [
        Stripped(
            f"""\
/**
 * This iterator is always done as {interface_name}
 * references no other instances.
 */
class {iterator_over_cls} : public impl::IIterator {{
 public:
{I}{iterator_over_cls}(
{II}const std::shared_ptr<types::IClass>&
{I}) {{
{II}// Intentionally empty.
{I}}}

{I}void Start() override {{
{II}// Intentionally empty.
{I}}}

{I}void Next() override {{
{II}throw std::logic_error(
{III}"You want to move "
{III}"an {iterator_over_cls}, "
{III}"but the iterator is always done as "
{III}"{interface_name} "
{III}"references no other instances."
{II});
{I}}}

{I}bool Done() const override {{
{II}return true;
{I}}}

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}throw std::logic_error(
{III}"You want to get from an {iterator_over_cls}, "
{III}"but the iterator is always done as "
{III}"{interface_name} references "
{III}"no other instances."
{II});
{I}}}

{I}long Index() const override {{
{II}return -1;
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<{iterator_over_cls}>(*this);
{I}}}

{I}void PrependToPath(Path*) const override {{
{II}throw std::logic_error(
{III}"You want to prepend to path from an {iterator_over_cls}, "
{III}"but the iterator is always done as "
{III}"{interface_name} references "
{III}"no other instances."
{II});
{I}}}

{I}~{iterator_over_cls}() override = default;
}};  // class {iterator_over_cls}"""
        )
    ]


@require(lambda iterator_qualities: len(iterator_qualities.relevant_properties) > 0)
def _generate_iterator_over_cls_execute_implementation(
    iterator_qualities: IteratorQualities,
) -> Stripped:
    """Generate the implementation of ``Execute()`` member."""
    cls = iterator_qualities.cls

    flow = [
        yielding_flow.command_from_text(
            """\
property_.reset();
item_ = nullptr;
index_ = -1;
done_ = false;"""
        )
    ]  # type: List[yielding_flow.Node]

    if iterator_qualities.cls_contains_a_list_or_tuple_property:
        flow.append(yielding_flow.command_from_text("cursor_.reset();"))

    for prop in iterator_qualities.relevant_properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        getter_name = cpp_naming.getter_name(prop.name)
        property_literal = cpp_naming.enum_literal_name(prop.name)

        if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                flow.append(
                    yielding_flow.IfTrue(
                        f"casted_->{getter_name}().has_value()",
                        [
                            yielding_flow.command_from_text(
                                f"""\
property_ = Property::{property_literal};
item_ = std::move(
{I}std::static_pointer_cast<types::IClass>(
{II}*(casted_->{getter_name}())
{I})
);
++index_;"""
                            ),
                            yielding_flow.Yield(),
                        ],
                    )
                )
            else:
                flow.append(
                    yielding_flow.command_from_text(
                        f"""\
property_ = Property::{property_literal};
item_ = std::move(
{I}std::static_pointer_cast<types::IClass>(
{II}casted_->{getter_name}()
{I})
);
++index_;"""
                    )
                )
                flow.append(yielding_flow.Yield())

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.OurTypeAnnotation
            ) and isinstance(
                type_anno.items.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ), (
                f"NOTE (mristin): We expect only lists of classes "
                f"at the moment, but you specified {prop.type_annotation} "
                f"in class {cls.name!r} and property {prop.name!r}. "
                f"Please contact the developers if you need this feature."
            )

            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                list_type = cpp_common.generate_type_with_const_ref_if_applicable(
                    type_annotation=prop.type_annotation.value,
                    types_namespace=cpp_common.TYPES_NAMESPACE,
                )
                list_var = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

                flow.append(
                    yielding_flow.IfTrue(
                        f"casted_->{getter_name}().has_value()",
                        [
                            yielding_flow.command_from_text(
                                f"property_ = Property::{property_literal};"
                            ),
                            yielding_flow.For(
                                f"*cursor_ < casted_->{getter_name}()->size()",
                                "++(*cursor_);",
                                [
                                    yielding_flow.command_from_text(
                                        f"""\
{list_type} {list_var}(
{I}*(casted_->{getter_name}())
);

item_ = std::move(
{I}std::static_pointer_cast<types::IClass>(
{II}{list_var}[*cursor_]
{I})
);
++index_;"""
                                    ),
                                    yielding_flow.Yield(),
                                ],
                                init="cursor_ = 0;",
                            ),
                            yielding_flow.command_from_text("cursor_.reset();"),
                        ],
                    )
                )
            else:
                list_type = cpp_common.generate_type_with_const_ref_if_applicable(
                    type_annotation=prop.type_annotation,
                    types_namespace=cpp_common.TYPES_NAMESPACE,
                )
                list_var = cpp_naming.variable_name(Identifier(f"the_{prop.name}"))

                flow.append(
                    yielding_flow.command_from_text(
                        f"property_ = Property::{property_literal};"
                    )
                )
                flow.append(
                    yielding_flow.For(
                        f"*cursor_ < casted_->{getter_name}().size()",
                        "++(*cursor_);",
                        [
                            yielding_flow.command_from_text(
                                f"""\
{list_type} {list_var}(
{I}casted_->{getter_name}()
);

item_ = std::move(
{I}std::static_pointer_cast<types::IClass>(
{II}{list_var}[*cursor_]
{I})
);
++index_;"""
                            ),
                            yielding_flow.Yield(),
                        ],
                        init="cursor_ = 0;",
                    )
                )
                flow.append(yielding_flow.command_from_text("cursor_.reset();"))

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            class_indices = [
                i
                for i, item_type_anno in enumerate(type_anno.items)
                if isinstance(item_type_anno, intermediate.OurTypeAnnotation)
                and isinstance(
                    item_type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                )
            ]
            assert len(class_indices) > 0, (
                "Expected at least one class item in the tuple as the property "
                "has been recognized as relevant in ``IteratorQualities``"
            )

            # NOTE (mristin):
            # Unlike lists, tuple items live at fixed, compile-time-known positions,
            # so we do not need a persistent local variable referring to the tuple
            # itself. Instead, we re-evaluate the getter and index into it with
            # ``std::get`` directly in each self-contained command, since a local
            # variable declared in one command would go out of scope after
            # the following ``Yield`` -- each command ends up in its own ``case``
            # block once the control flow is linearized into a co-routine.
            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                tuple_getter_expr = Stripped(f"*(casted_->{getter_name}())")
            else:
                tuple_getter_expr = Stripped(f"casted_->{getter_name}()")

            yield_nodes = []  # type: List[yielding_flow.Node]
            for i in class_indices:
                yield_nodes.append(
                    yielding_flow.command_from_text(
                        f"""\
cursor_ = {i};
item_ = std::move(
{I}std::static_pointer_cast<types::IClass>(
{II}std::get<{i}>({tuple_getter_expr})
{I})
);
++index_;"""
                    )
                )
                yield_nodes.append(yielding_flow.Yield())

            if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
                flow.append(
                    yielding_flow.IfTrue(
                        f"casted_->{getter_name}().has_value()",
                        [
                            yielding_flow.command_from_text(
                                f"property_ = Property::{property_literal};"
                            ),
                            *yield_nodes,
                            yielding_flow.command_from_text("cursor_.reset();"),
                        ],
                    )
                )
            else:
                flow.append(
                    yielding_flow.command_from_text(
                        f"property_ = Property::{property_literal};"
                    )
                )
                flow.extend(yield_nodes)
                flow.append(yielding_flow.command_from_text("cursor_.reset();"))

    flow.append(
        yielding_flow.command_from_text(
            """\
done_ = true;
index_ = -1;"""
        )
    )

    body = cpp_yielding.generate_execute_body(
        flow=flow, state_member=Identifier("state_")
    )

    iterator_name = cpp_naming.class_name(Identifier(f"Iterator_over_{cls.name}"))

    return Stripped(
        f"""\
void {iterator_name}::Execute() {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


@require(lambda iterator_qualities: len(iterator_qualities.relevant_properties) > 0)
def _generate_iterator_over_cls(
    iterator_qualities: IteratorQualities,
) -> List[Stripped]:
    """Generate a non-recursive iterator over referenced instances."""
    cls = iterator_qualities.cls

    iterator_name = cpp_naming.class_name(Identifier(f"Iterator_over_{cls.name}"))

    interface_name = cpp_naming.interface_name(cls.name)

    private_properties = [
        Stripped(
            """\
// We make instance_ a pointer, so that we can follow the rule-of-zero.
const std::shared_ptr<types::IClass>* instance_;"""
        ),
        Stripped(
            f"""\
// We make casted_ a pointer, so that we can follow the rule-of-zero.
const types::{interface_name}* casted_;"""
        ),
        Stripped("std::uint32_t state_;"),
        Stripped("common::optional<Property> property_;"),
    ]
    if iterator_qualities.cls_contains_a_list_or_tuple_property:
        private_properties.append(
            Stripped("common::optional<size_t> cursor_;  // in yield-from loops")
        )

    private_properties.extend(
        (
            Stripped("std::shared_ptr<types::IClass> item_;"),
            Stripped("long index_;  // in total iteration"),
            Stripped("bool done_;"),
        )
    )

    private_properties_joined = "\n".join(private_properties)

    execute_block = _generate_iterator_over_cls_execute_implementation(
        iterator_qualities=iterator_qualities
    )

    if iterator_qualities.cls_contains_a_list_or_tuple_property:
        prepend_to_path_block = Stripped(
            f"""\
void {iterator_name}::PrependToPath(
{I}Path* path
) const {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to prepend to path from {iterator_name}, "
{III}"but the iterator was done."
{II});
{I}}}
{I}#endif

{I}if (cursor_.has_value()) {{
{II}path->segments.emplace_front(
{III}common::make_unique<IndexSegment>(*cursor_)
{II});
{I}}}

{I}#ifdef DEBUG
{I}if (!property_.has_value()) {{
{II}throw std::logic_error(
{III}"You want to prepend to path from {iterator_name}, "
{III}"but the property_ has not been set to a value."
{II});
{I}}}
{I}#endif

{I}path->segments.emplace_front(
{II}common::make_unique<PropertySegment>(*property_)
{I});
}}"""
        )

    else:
        prepend_to_path_block = Stripped(
            f"""\
void {iterator_name}::PrependToPath(
{I}Path* path
) const {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to prepend to path from {iterator_name}, "
{III}"but the iterator was done."
{II});
{I}}}

{I}if (!property_.has_value()) {{
{II}throw std::logic_error(
{III}"You want to prepend to path from {iterator_name}, "
{III}"but the property_ has not been set to a value."
{II});
{I}}}
{I}#endif

{I}path->segments.emplace_front(
{II}common::make_unique<PropertySegment>(*property_)
{I});
}}"""
        )

    return [
        Stripped(
            f"""\
/**
 * Iterate non-recursively over the instances referenced from an instance.
 */
class {iterator_name} : public impl::IIterator {{
 public:
{I}{iterator_name}(
{II}const std::shared_ptr<types::IClass>& instance
{I});
{I}void Start() override;
{I}void Next() override;
{I}bool Done() const override;
{I}const std::shared_ptr<types::IClass>& Get() const override;
{I}long Index() const override;
{I}void PrependToPath(Path* path) const override;
{I}std::unique_ptr<impl::IIterator> Clone() const override;
{I}~{iterator_name}() override = default;

 private:
{I}{indent_but_first_line(private_properties_joined, I)}

{I}void Execute();
}};  // class {iterator_name}"""
        ),
        Stripped(
            f"""\
{iterator_name}::{iterator_name}(
{I}const std::shared_ptr<types::IClass>& instance
) :
{I}instance_(&instance),
{I}// NOTE (mristin):
{I}// The dynamic cast is necessary due to virtual inheritance. Otherwise,
{I}// we would have used static cast.
{I}casted_(
{II}dynamic_cast<types::{interface_name}*>(
{III}instance.get()
{II})
{I}) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
void {iterator_name}::Start() {{
{I}state_ = 0;
{I}Execute();
}}"""
        ),
        Stripped(
            f"""\
void {iterator_name}::Next() {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to move {iterator_name}, "
{III}"but it was done."
{II});
{I}}}
{I}#endif

{I}Execute();
}}"""
        ),
        Stripped(
            f"""\
bool {iterator_name}::Done() const {{
{I}return done_;
}}"""
        ),
        Stripped(
            f"""\
const std::shared_ptr<types::IClass>& {iterator_name}::Get() const {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to get from {iterator_name}, "
{III}"but the iterator was done."
{II});
{I}}}
{I}#endif

{I}return item_;
}}"""
        ),
        Stripped(
            f"""\
long {iterator_name}::Index() const {{
{I}#ifdef DEBUG
{I}if (Done() && index_ != -1) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected index to be -1 "
{IIII}"from a done {iterator_name}, "
{IIII}"but got: ",
{IIII}std::to_string(index_)
{III})
{II});
{I}}}
{I}#endif

{I}return index_;
}}"""
        ),
        prepend_to_path_block,
        Stripped(
            f"""\
std::unique_ptr<impl::IIterator> {iterator_name}::Clone() const {{
{I}return common::make_unique<{iterator_name}>(*this);
}}"""
        ),
        execute_block,
    ]


def _generate_iteration_over_cls(cls: intermediate.ConcreteClass) -> List[Stripped]:
    """Generate the iterator over the given class."""
    iterator_qualities = IteratorQualities(cls=cls)

    if len(iterator_qualities.relevant_properties) == 0:
        return _generate_empty_iterator_over_cls(iterator_qualities=iterator_qualities)

    interface_name = cpp_naming.interface_name(cls.name)

    return [
        Stripped(f"// region Non-recursive iteration over {interface_name}"),
        *_generate_iterator_over_cls(iterator_qualities=iterator_qualities),
        Stripped("// endregion"),
    ]


def _generate_new_non_recursive_iterator_function(
    symbol_table: intermediate.SymbolTable,
) -> Stripped:
    """Generate the factory for non-recursive iterators."""
    case_blocks = []  # type: List[Stripped]

    for cls in symbol_table.concrete_classes:
        enum_name = cpp_naming.enum_name(Identifier("Model_type"))
        literal_name = cpp_naming.enum_literal_name(cls.name)

        iterator_over_cls = cpp_naming.class_name(
            Identifier(f"Iterator_over_{cls.name}")
        )

        case_blocks.append(
            Stripped(
                f"""\
case types::{enum_name}::{literal_name}:
{I}return common::make_unique<{iterator_over_cls}>(
{II}instance
{I});"""
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
{IIII}static_cast<std::uint32_t>(instance->model_type())
{III})
{II})
{I});"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    switch_stmt = Stripped(
        f"""\
switch (instance->model_type()) {{
{I}{indent_but_first_line(case_blocks_joined, I)}
}}"""
    )

    new_non_recursive_iterator = cpp_naming.function_name(
        Identifier("new_non_recursive_iterator")
    )

    return Stripped(
        f"""\
/**
 * Produce a non-recursive iterator over the instance given its runtime model type.
 */
std::unique_ptr<impl::IIterator> {new_non_recursive_iterator}(
{I}const std::shared_ptr<types::IClass>& instance
) {{
{I}{indent_but_first_line(switch_stmt, I)}
}}"""
    )


def _generate_recursive_inclusive_iterator_execute() -> Stripped:
    """Generate the ``Execute()`` method of the recursive inclusive iterator."""
    new_non_recursive_iterator = cpp_naming.function_name(
        Identifier("new_non_recursive_iterator")
    )

    flow = [
        yielding_flow.command_from_text(
            """\
item_ = instance_;
index_ = 0;
done_ = false;
non_recursive_iterator_.reset(nullptr);
recursive_iterator_.reset(nullptr);"""
        ),
        yielding_flow.Yield(),
        yielding_flow.command_from_text(
            f"""\
non_recursive_iterator_ = {new_non_recursive_iterator}(
{I}*instance_
);"""
        ),
        yielding_flow.For(
            "!non_recursive_iterator_->Done()",
            "non_recursive_iterator_->Next();",
            [
                yielding_flow.command_from_text(
                    """\
item_ = &(non_recursive_iterator_->Get());
++index_;"""
                ),
                yielding_flow.Yield(),
                yielding_flow.command_from_text(
                    f"""\
recursive_iterator_ = std::move(
{I}common::make_unique<RecursiveExclusiveIterator>(
{II}*item_
{I})
);"""
                ),
                yielding_flow.For(
                    "!recursive_iterator_->Done()",
                    "recursive_iterator_->Next();",
                    [
                        yielding_flow.command_from_text(
                            """\
item_ = &(recursive_iterator_->Get());
++index_;"""
                        ),
                        yielding_flow.Yield(),
                    ],
                    init="recursive_iterator_->Start();",
                ),
                yielding_flow.command_from_text("recursive_iterator_.reset(nullptr);"),
            ],
            init="non_recursive_iterator_->Start();",
        ),
        yielding_flow.command_from_text(
            """\
non_recursive_iterator_.reset(nullptr);
done_ = true;
index_ = -1;"""
        ),
    ]  # type: List[yielding_flow.Node]

    body = cpp_yielding.generate_execute_body(
        flow=flow, state_member=Identifier("state_")
    )

    return Stripped(
        f"""\
void RecursiveInclusiveIterator::Execute() {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_recursive_iteration() -> List[Stripped]:
    """Generate the iterator to recursively iterate over the referenced instances."""
    execute_block = _generate_recursive_inclusive_iterator_execute()

    return [
        Stripped(
            f"""\
/**
 * Iterate recursively over the instance, including the instance in the iteration.
 *
 * This is a realisation of the following pseudo-code:
 * \\code
 * stack = new Stack();
 * stack.push(instance);
 * while not stack.empty():
 *     instance = stack.pop()
 *     yield instance
 *
 *     it = new_non_recursive_iterator(instance)
 *     while not it.done():
 *         yield recursively from it.get()
 *         it.next()
 * \\endcode
 */
class RecursiveInclusiveIterator : public impl::IIterator {{
 public:
{I}RecursiveInclusiveIterator(
{II}const std::shared_ptr<types::IClass>& instance
{I});

{I}RecursiveInclusiveIterator(
{II}const RecursiveInclusiveIterator& other
{I});
{I}RecursiveInclusiveIterator(
{II}RecursiveInclusiveIterator&& other
{I});
{I}RecursiveInclusiveIterator& operator=(
{II}const RecursiveInclusiveIterator& other
{I});
{I}RecursiveInclusiveIterator& operator=(
{II}RecursiveInclusiveIterator&& other
{I});

{I}void Start() override;
{I}void Next() override;
{I}bool Done() const override;
{I}const std::shared_ptr<types::IClass>& Get() const override;
{I}long Index() const override;
{I}void PrependToPath(Path* path) const override;
{I}std::unique_ptr<impl::IIterator> Clone() const override;
{I}~RecursiveInclusiveIterator() override = default;

 private:
{I}// The instance_ needs to be a pointer so that we can re-assign it in
{I}// the constructors and assignment operations.
{I}const std::shared_ptr<types::IClass>* instance_;

{I}// Iterator over the instances referenced from this instance
{I}// in the outer loop
{I}std::unique_ptr<impl::IIterator> non_recursive_iterator_;

{I}// Iterator for recursion into the reference referenced from this instance
{I}// in the inner loop
{I}std::unique_ptr<impl::IIterator> recursive_iterator_;

{I}const std::shared_ptr<types::IClass>* item_;

{I}bool done_;
{I}long index_;
{I}size_t state_;

{I}void Execute();
}};  // class RecursiveInclusiveIterator"""
        ),
        Stripped(
            f"""\
/**
 * Iterate recursively over the instance, excluding the instance in the iteration.
 *
 * This is a realisation of the following pseudo-code:
 * \\code
 * stack = new Stack();
 * stack.push(instance);
 * while not stack.empty():
 *     some_instance = stack.pop()
 *     if some_instance is not instance:
 *         yield some_instance
 *
 *     it = new_non_recursive_iterator(some_instance)
 *     while not it.done():
 *         yield recursively from it.get()
 *         it.next()
 * \\endcode
 */
class RecursiveExclusiveIterator : public impl::IIterator {{
 public:
{I}RecursiveExclusiveIterator(
{II}const std::shared_ptr<types::IClass>& instance
{I});

{I}void Start() override;
{I}void Next() override;
{I}bool Done() const override;
{I}const std::shared_ptr<types::IClass>& Get() const override;
{I}long Index() const override;
{I}void PrependToPath(Path* path) const override;
{I}std::unique_ptr<impl::IIterator> Clone() const override;
{I}~RecursiveExclusiveIterator() override = default;

 private:
{I}RecursiveInclusiveIterator inclusive_iterator_;
}};  // class RecursiveExclusiveIterator"""
        ),
        Stripped("// region RecursiveInclusiveIterator implementation"),
        Stripped(
            f"""\
RecursiveInclusiveIterator::RecursiveInclusiveIterator(
{I}const std::shared_ptr<types::IClass>& instance
) : instance_(&instance), item_(nullptr), index_(-1) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
RecursiveInclusiveIterator::RecursiveInclusiveIterator(
{I}const RecursiveInclusiveIterator& other
) {{
{I}instance_ = other.instance_;
{I}non_recursive_iterator_ = (other.non_recursive_iterator_ == nullptr)
{II}? nullptr
{II}: other.non_recursive_iterator_->Clone();
{I}recursive_iterator_ = (other.recursive_iterator_ == nullptr)
{II}? nullptr
{II}: other.recursive_iterator_->Clone();
{I}item_ = other.item_;
{I}done_ = other.done_;
{I}index_ = other.index_;
{I}state_ = other.state_;
}}"""
        ),
        Stripped(
            f"""\
RecursiveInclusiveIterator::RecursiveInclusiveIterator(
{I}RecursiveInclusiveIterator&& other
) {{
{I}instance_ = other.instance_;
{I}non_recursive_iterator_ = std::move(other.non_recursive_iterator_);
{I}recursive_iterator_ = std::move(other.recursive_iterator_);
{I}item_ = other.item_;
{I}done_ = other.done_;
{I}index_ = other.index_;
{I}state_ = other.state_;
}}"""
        ),
        Stripped(
            f"""\
RecursiveInclusiveIterator& RecursiveInclusiveIterator::operator=(
{I}const RecursiveInclusiveIterator& other
) {{
{I}return *this = RecursiveInclusiveIterator(other);
}}"""
        ),
        Stripped(
            f"""\
RecursiveInclusiveIterator& RecursiveInclusiveIterator::operator=(
{I}RecursiveInclusiveIterator&& other
) {{
{I}if (this != &other) {{
{II}instance_ = other.instance_;
{II}non_recursive_iterator_ = std::move(other.non_recursive_iterator_);
{II}recursive_iterator_ = std::move(other.recursive_iterator_);
{II}item_ = other.item_;
{II}done_ = other.done_;
{II}index_ = other.index_;
{II}state_ = other.state_;
{I}}}

{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
void RecursiveInclusiveIterator::Start() {{
{I}state_ = 0;
{I}Execute();

{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"Expected RecursiveInclusiveIterator not to be done at start, but it was."
{II});
{I}}}

{I}if (Index() !== 0) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected RecursiveInclusiveIterator::Index() to be 0 on Start()"
{IIII}", but got ",
{IIII}std::to_string(Index())
{III})
{II});
{I}}}

{I}const std::shared_ptr<IClass>& current_item(Get());
{I}if (current_item == nullptr) {{
{II}throw std::logic_error(
{III}"Unexpected null pointer from Get() at the end of "
{III}"RecursiveInclusiveIterator::Start"
{II});
{I}}}

{I}if (current_item.get() != instance_.get()) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected the current item to point to the instance "
{IIII}"at the end of RecursiveInclusiveIterator::Start, "
{IIII}"but got ",
{IIII}std::to_string(current_item.get()),
{IIII}" from Get() instead of ",
{IIII}std::to_string(instance_.get())
{III})
{II});
{I}}}
{I}#endif
}}"""
        ),
        Stripped(
            f"""\
void RecursiveInclusiveIterator::Next() {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to move a RecursiveInclusiveIterator, but it was done."
{II});
{I}}}
{I}#endif

{I}Execute();
}}"""
        ),
        Stripped(
            f"""\
bool RecursiveInclusiveIterator::Done() const {{
{I}return done_;
}}"""
        ),
        Stripped(
            f"""\
const std::shared_ptr<types::IClass>& RecursiveInclusiveIterator::Get() const {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to get from RecursiveInclusiveIterator, but it was done."
{II});
{I}}}

{I}if (item_ == nullptr) {{
{II}throw std::logic_error(
{III}"You want to get from a RecursiveInclusiveIterator, "
{III}"but item_ has not been set."
{II});
{I}}}
{I}#endif

{I}return *item_;
}}"""
        ),
        Stripped(
            f"""\
long RecursiveInclusiveIterator::Index() const {{
{I}#ifdef DEBUG
{I}if (Done() && index_ != -1) {{
{II}throw std::logic_error(
{III}common::Concat(
{IIII}"Expected index to be -1 on a done RecursiveInclusiveIterator, "
{IIII}"but got: ",
{IIII}std::to_string(index_)
{III})
{II});
{I}}}
{I}#endif

{I}return index_;
}}"""
        ),
        Stripped(
            f"""\
void RecursiveInclusiveIterator::PrependToPath(Path* path) const {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to prepend to path from RecursiveInclusiveIterator, "
{III}"but the iterator was done."
{II});
{I}}}
{I}#endif

{I}if (Index() == 0) {{
{II}// Index set to 0 indicates that the iterator points to the instance itself.
{II}// Therefore, there is nothing to prepend to the path.
{II}return;
{I}}}

{I}if (recursive_iterator_ != nullptr) {{
{II}recursive_iterator_->PrependToPath(path);
{I}}}

{I}if (non_recursive_iterator_ != nullptr) {{
{II}non_recursive_iterator_->PrependToPath(path);
{I}}}
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<impl::IIterator> RecursiveInclusiveIterator::Clone() const {{
{I}return common::make_unique<RecursiveInclusiveIterator>(*this);
}}"""
        ),
        execute_block,
        Stripped("// endregion RecursiveInclusiveIterator implementation"),
        Stripped("// region RecursiveExclusiveIterator implementation"),
        Stripped(
            f"""\
RecursiveExclusiveIterator::RecursiveExclusiveIterator(
{I}const std::shared_ptr<types::IClass>& instance
) : inclusive_iterator_(instance) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
void RecursiveExclusiveIterator::Start() {{
{I}inclusive_iterator_.Start();

{I}#ifdef DEBUG
{I}if (inclusive_iterator_.Done()) {{
{II}throw std::logic_error(
{III}"Expected the inclusive iterator to be not-done immediately after start, "
{III}"as the first item is expected to point to the instance itself, "
{III}"but the inclusive iterator was done."
{II});
{I}}}
{I}#endif

{I}// Simply skip the instance in the very first yield.
{I}inclusive_iterator_.Next();
}}"""
        ),
        Stripped(
            f"""\
void RecursiveExclusiveIterator::Next() {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to move a RecursiveExclusiveIterator, but it was done."
{II});
{I}}}
{I}#endif

{I}inclusive_iterator_.Next();
}}"""
        ),
        Stripped(
            f"""\
bool RecursiveExclusiveIterator::Done() const {{
{I}return inclusive_iterator_.Done();
}}"""
        ),
        Stripped(
            f"""\
const std::shared_ptr<types::IClass>& RecursiveExclusiveIterator::Get() const {{
{I}#ifdef DEBUG
{I}if (Done()) {{
{II}throw std::logic_error(
{III}"You want to get from RecursiveExclusiveIterator, but it was done."
{II});
{I}}}
{I}#endif

{I}return inclusive_iterator_.Get();
}}"""
        ),
        Stripped(
            f"""\
long RecursiveExclusiveIterator::Index() const {{
{I}if (inclusive_iterator_.Done()) {{
{II}return -1;
{I}}}

{I}return inclusive_iterator_.Index() - 1;
}}"""
        ),
        Stripped(
            f"""\
void RecursiveExclusiveIterator::PrependToPath(Path* path) const {{
{I}inclusive_iterator_.PrependToPath(path);
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<impl::IIterator> RecursiveExclusiveIterator::Clone() const {{
{I}return common::make_unique<RecursiveExclusiveIterator>(*this);
}}"""
        ),
        Stripped("// endregion RecursiveExclusiveIterator implementation"),
    ]


def _generate_descent_and_descent_once_implementations() -> List[Stripped]:
    """Generate the implementation of the descent iterables."""
    new_non_recursive_iterator = cpp_naming.function_name(
        Identifier("new_non_recursive_iterator")
    )

    return [
        Stripped(
            f"""\
// region Descent

// NOTE (mristin):
// We have to make a copy of the pointer since we would lose otherwise
// in range-based `for` loops,
// see: https://stackoverflow.com/questions/29990045/temporary-lifetime-in-range-for-expression
Descent::Descent(
{I}std::shared_ptr<types::IClass> instance
) : instance_(std::move(instance)) {{
{I}// Intentionally empty.
}}

Iterator Descent::begin() const {{
{I}std::unique_ptr<impl::IIterator> it_impl(
{II}std::move(
{III}common::make_unique<RecursiveExclusiveIterator>(instance_)
{II})
{I});

{I}it_impl->Start();

{I}// NOTE(mristin):
{I}// We short-circuit here for memory frugality,
{I}// as we can immediately dispose it_impl.
{I}if (it_impl->Done()) {{
{II}return end();
{I}}}

{I}return Iterator(std::move(it_impl));
}}

const Iterator& Descent::end() const {{
{I}static Iterator iterator(common::make_unique<AlwaysDoneIterator>());
{I}return iterator;
}}

// endregion Descent"""
        ),
        Stripped(
            f"""\
// region DescentOnce

// NOTE (mristin):
// We have to make a copy of the pointer since we would lose otherwise
// in range-based `for` loops,
// see: https://stackoverflow.com/questions/29990045/temporary-lifetime-in-range-for-expression
DescentOnce::DescentOnce(
{I}std::shared_ptr<types::IClass> instance
) : instance_(std::move(instance)) {{
{I}// Intentionally empty.
}}

Iterator DescentOnce::begin() const {{
{I}std::unique_ptr<impl::IIterator> it_impl(
{II}{new_non_recursive_iterator}(instance_)
{I});

{I}it_impl->Start();

{I}// NOTE(mristin):
{I}// We short-circuit here for efficiency, as we can immediately dispose it_impl.
{I}if (it_impl->Done()) {{
{II}return Iterator(std::move(common::make_unique<AlwaysDoneIterator>()));
{I}}}

{I}return Iterator(std::move(it_impl));
}}

const Iterator& DescentOnce::end() const {{
{I}static Iterator iterator(common::make_unique<AlwaysDoneIterator>());
{I}return iterator;
}}

// endregion DescentOnce"""
        ),
    ]


def _generate_constructor_implementation(cls: intermediate.ConcreteClass) -> Stripped:
    """Transpile the constructor implementation for the given ``cls``."""
    assert all(
        isinstance(stmt, intermediate_construction.AssignArgument)
        for stmt in cls.constructor.inlined_statements
    ), (
        f"We expect only assigns in the inlined constructors, "
        f"but got for class {cls.name!r}: {cls.constructor.inlined_statements}"
    )

    body_statements = []  # type: List[Stripped]

    for stmt in cls.constructor.inlined_statements:
        assert isinstance(stmt, intermediate_construction.AssignArgument), (
            f"Only assigns expected in inlined constructors, but got the following "
            f"statement for the class {cls.name!r}: {stmt}"
        )

        prop_member = cpp_naming.private_property_name(stmt.name)
        arg_name = cpp_naming.argument_name(stmt.argument)

        if stmt.default is not None:
            if isinstance(stmt.default, intermediate_construction.EmptyList):
                body_statements.append(
                    Stripped(
                        f"""\
if ({arg_name}.has_value()) {{
{I}{prop_member} = *{arg_name};
}} else {{
{I}{prop_member}.emplace();
}}"""
                    )
                )
            elif isinstance(stmt.default, intermediate_construction.DefaultEnumLiteral):
                enum_name = cpp_naming.enum_name(stmt.default.enum.name)
                literal_name = cpp_naming.enum_literal_name(stmt.default.literal.name)

                body_statements.append(
                    Stripped(
                        f"""\
{prop_member} = ({arg_name}.has_value())
{I}? *{arg_name}
{I}: {enum_name}::{literal_name};"""
                    )
                )
            else:
                # noinspection PyTypeChecker
                assert_never(stmt.default)

        else:
            prop = cls.properties_by_name[stmt.name]
            if cpp_common.is_referencable(prop.type_annotation):
                body_statements.append(
                    Stripped(f"{prop_member} = std::move({arg_name});")
                )
            else:
                body_statements.append(Stripped(f"{prop_member} = {arg_name};"))

    body = (
        "\n\n".join(body_statements)
        if len(body_statements) > 0
        else "// Intentionally empty."
    )

    cls_name = cpp_naming.class_name(cls.name)

    if len(cls.constructor.arguments) == 0:
        return Stripped(
            f"""\
{cls_name}::{cls_name}() {{
{I}{indent_but_first_line(body, I)}
}}"""
        )

    constructor_argument_specs = []  # type: List[str]
    for arg in cls.constructor.arguments:
        arg_type = cpp_common.generate_type(arg.type_annotation)
        arg_name = cpp_naming.argument_name(arg.name)

        constructor_argument_specs.append(f"{arg_type} {arg_name}")

    constructor_arguments_specs_joined = ",\n".join(constructor_argument_specs)

    return Stripped(
        f"""\
{cls_name}::{cls_name}(
{I}{indent_but_first_line(constructor_arguments_specs_joined, I)}
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_always_done_iterator() -> Stripped:
    """Generate the definition and implementation of the end-of-descent iterator."""
    return Stripped(
        f"""\
/**
 * This iterator is always done.
 *
 * It is used for efficient comparisons against end-of-descent.
 */
class AlwaysDoneIterator : public impl::IIterator {{
 public:
{I}void Start() override {{
{II}// Intentionally empty.
{I}}}

{I}void Next() override {{
{II}throw std::logic_error(
{III}"You want to move an AlwaysDoneIterator, "
{III}"but the iterator is always done, as its name suggests."
{II});
{I}}}

{I}bool Done() const override {{
{II}return true;
{I}}}

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}throw std::logic_error(
{III}"You want to get from an AlwaysDoneIterator, "
{III}"but the iterator is always done, as its name suggests."
{II});
{I}}}

{I}std::unique_ptr<IIterator> Clone() const override {{
{II}return common::make_unique<AlwaysDoneIterator>(*this);
{I}}};

{I}void PrependToPath(Path*) const override {{
{II}throw std::logic_error(
{III}"You want to prepend to path from an AlwaysDoneIterator, "
{III}"but the iterator is always done, as its name suggests."
{II});
{I}}}

{I}long Index() const override {{
{II}return -1;
{I}}}

{I}~AlwaysDoneIterator() override = default;
}};  // class AlwaysDoneIterator"""
    )


def _generate_iterator_implementation() -> List[Stripped]:
    """Generate the impl. of the facade ``Iterator`` around ``impl::Iterator``."""
    return [
        Stripped(
            f"""\
Iterator::Iterator(
{I}const Iterator& other
) : implementation_(other.implementation_->Clone()) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Iterator::Iterator(
{I}Iterator&& other
) : implementation_(std::move(other.implementation_)) {{
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
{II}this->implementation_ = std::move(other.implementation_);
{I}}}

{I}return *this;
}}"""
        ),
        Stripped(
            f"""\
const std::shared_ptr<types::IClass>& Iterator::operator*() const {{
{I}if (implementation_->Done()) {{
{II}throw std::logic_error(
{III}"You want to dereference a completed iterator."
{II});
{I}}}

{I}return implementation_->Get();
}}"""
        ),
        Stripped(
            f"""\
const std::shared_ptr<types::IClass>* Iterator::operator->() {{
{I}if (implementation_->Done()) {{
{II}throw std::logic_error(
{III}"You want to dereference a completed iterator."
{II});
{I}}}

{I}return &(implementation_->Get());
}}"""
        ),
        Stripped(
            f"""\
// Prefix increment
Iterator& Iterator::operator++() {{
{I}if (implementation_->Done()) {{
{II}throw std::logic_error(
{III}"You want to move a completed iterator."
{II});
{I}}}

{I}implementation_->Next();
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
{I}return a.implementation_->Index() == b.implementation_->Index();
}}"""
        ),
        Stripped(
            f"""\
bool operator!=(const Iterator& a, const Iterator& b) {{
{I}return a.implementation_->Index() != b.implementation_->Index();
}}"""
        ),
        Stripped(
            f"""\
Path MaterializePath(const Iterator& iterator) {{
{I}if (iterator.implementation_->Done()) {{
{II}throw std::logic_error(
{III}"You want to materialize path of a completed iterator."
{II});
{I}}}

{I}Path path;
{I}iterator.implementation_->PrependToPath(&path);
{I}return path;
}}"""
        ),
        Stripped(
            f"""\
void PrependToPath(const Iterator& iterator, Path* path) {{
{I}if (iterator.implementation_->Done()) {{
{II}throw std::logic_error(
{III}"You want to prepend a path of a completed iterator."
{II});
{I}}}

{I}iterator.implementation_->PrependToPath(path);
}}"""
        ),
    ]


def _generate_over_enum_implementation(enum: intermediate.Enumeration) -> Stripped:
    """Generate the implementation for a container over ``enum`` literals."""
    enum_name = cpp_naming.enum_name(enum.name)
    over_enum = cpp_naming.constant_name(Identifier(f"over_{enum.name}"))

    literals = []  # type: List[Stripped]
    for literal in enum.literals:
        literal_name = cpp_naming.enum_literal_name(literal.name)
        literals.append(Stripped(f"types::{enum_name}::{literal_name}"))

    literals_joined = ",\n".join(literals)

    return Stripped(
        f"""\
const std::vector<types::{enum_name}> {over_enum} = {{
{I}{indent_but_first_line(literals_joined, I)}
}};"""
    )


# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate implementation of functions to iterate over instances."""
    namespace = Stripped(f"{library_namespace}::iteration")

    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks = [
        cpp_common.WARNING,
        Stripped(
            f'''\
#include "{include_prefix_path}/common.hpp"
#include "{include_prefix_path}/iteration.hpp"'''
        ),
        cpp_common.generate_namespace_opening(namespace),
        Stripped("// region Pathing"),
        _generate_property_to_wstring_implementation(symbol_table=symbol_table),
        *_generate_property_segment_implementation(),
        *_generate_index_segment_implementation(),
        *_generate_path_implementation(),
        Stripped("// endregion Pathing"),
        Stripped("// region Non-recursive iteration"),
    ]  # type: List[Stripped]

    errors = []  # type: List[Error]

    for cls in symbol_table.concrete_classes:
        if cls.is_implementation_specific:
            errors.append(
                Error(
                    cls.parsed.node,
                    f"NOTE (mristin): "
                    f"The class {cls.name!r} is marked as implementation specific. "
                    f"However, we currently do not generate the C++ iteration code "
                    f"over implementation-specific classes. Please contact "
                    f"the developers if you need this feature.",
                )
            )
            continue

        blocks.extend(_generate_iteration_over_cls(cls=cls))

    blocks.append(_generate_always_done_iterator())

    blocks.append(
        _generate_new_non_recursive_iterator_function(symbol_table=symbol_table)
    )

    blocks.append(Stripped("// endregion Non-recursive iteration"))

    blocks.append(Stripped("// region Recursive iteration"))

    blocks.extend(_generate_recursive_iteration())

    blocks.append(Stripped("// endregion Recursive iteration"))

    blocks.append(Stripped("// region Iterator facade"))

    blocks.extend(_generate_iterator_implementation())

    blocks.append(Stripped("// endregion Iterator facade"))

    blocks.append(Stripped("// region Descents"))

    blocks.extend(_generate_descent_and_descent_once_implementations())

    blocks.append(Stripped("// endregion Descents"))

    if len(symbol_table.enumerations) > 0:
        blocks.append(Stripped("// region Over enumerations"))

        for enum in symbol_table.enumerations:
            blocks.append(_generate_over_enum_implementation(enum))

        blocks.append(Stripped("// endregion Over enumerations"))

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


# endregion

assert generate_header.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_header_consistent(
    module_doc=__doc__, generate_header_doc=generate_header.__doc__
)

assert generate_implementation.__doc__ is not None
cpp_common.assert_module_docstring_and_generate_implementation_consistent(
    module_doc=__doc__, generate_implementation_doc=generate_implementation.__doc__
)
