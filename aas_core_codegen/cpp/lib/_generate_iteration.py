"""Generate code of functions to iterate over instances."""

import io
import re
from typing import (
    AbstractSet,
    Dict,
    Set,
    Optional,
    List,
    Tuple,
    Sequence,
    Final,
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
    over as cpp_over,
)
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
)


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
 * \\brief Represent an access to a key of a JSON-able object on a path.
 *
 * Unlike \\ref PropertySegment, which points to one of the properties of
 * the meta-model, this segment points to a key of a JSON-able object, which
 * can be an arbitrary string known only at runtime.
 */
struct KeySegment : public ISegment {{
{I}/**
{I} * Key of the JSON-able object
{I} */
{I}std::wstring key;

{I}explicit KeySegment(
{II}std::wstring a_key
{I});

{I}std::wstring ToWstring() const override;
{I}std::unique_ptr<ISegment> Clone() const override;

{I}~KeySegment() override = default;
}};  // struct KeySegment"""
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

{I}/**
{I} * \\brief Append the segments leading to the current instance to the \\p path.
{I} *
{I} * Only called on request, so the iteration itself builds no paths.
{I} */
{I}virtual void AppendToPath(Path& path) const = 0;

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
 * a "yielding" iterator by composing iterators over the properties so that we
 * always keep the model stack as well as the properties iterated thus far.
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
{II}implementation_(std::move(implementation)),
{II}index_(implementation_->Done() ? -1 : 0) {{
{II}// Intentionally empty.
{I}}}

{I}std::unique_ptr<impl::IIterator> implementation_;

{I}/**
{I} * Count the instances iterated thus far so that we can compare the iterators,
{I} * or -1 if the iteration is done.
{I} */
{I}long index_;
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


def _generate_key_segment_implementation() -> List[Stripped]:
    """Generate the implementation of ``KeySegment`` struct."""
    return [
        Stripped("// region struct KeySegment"),
        Stripped(
            f"""\
KeySegment::KeySegment(std::wstring a_key) :
{I}key(std::move(a_key)) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
std::wstring KeySegment::ToWstring() const {{
{I}// NOTE (mristin):
{I}// We escape the key the same way a JSON string is escaped so that
{I}// the resulting path reads as a valid C++ expression on
{I}// a ``nlohmann::json`` value, *e.g.*, ``.some_property["some key"]``.

{I}std::wstring escaped;
{I}escaped.reserve(key.size());

{I}for (const wchar_t character : key) {{
{II}switch (character) {{
{III}case L'\\\\':
{IIII}escaped.append(L"\\\\\\\\");
{IIII}break;
{III}case L'"':
{IIII}escaped.append(L"\\\\\\"");
{IIII}break;
{III}case L'\\b':
{IIII}escaped.append(L"\\\\b");
{IIII}break;
{III}case L'\\f':
{IIII}escaped.append(L"\\\\f");
{IIII}break;
{III}case L'\\n':
{IIII}escaped.append(L"\\\\n");
{IIII}break;
{III}case L'\\r':
{IIII}escaped.append(L"\\\\r");
{IIII}break;
{III}case L'\\t':
{IIII}escaped.append(L"\\\\t");
{IIII}break;
{III}default:
{IIII}escaped.push_back(character);
{IIII}break;
{II}}}
{I}}}

{I}return common::Concat(
{II}L"[\\"",
{II}escaped,
{II}L"\\"]"
{I});
}}"""
        ),
        Stripped(
            f"""\
std::unique_ptr<ISegment> KeySegment::Clone() const {{
{I}return common::make_unique<KeySegment>(*this);
}}"""
        ),
        Stripped("// endregion struct KeySegment"),
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


# region Combinators

# NOTE (mristin):
# We iterate lazily over the model by combining the hand-written iterators below.
# They follow three rules so that we never build the iterators over the whole
# model up front:
#
# 1. ``ChainIterator`` starts a child only once the previous child is done.
# 2. ``DispatchingIterator`` dispatches on the instance only in ``Start()``.
# 3. ``EachIterator`` builds the iterator over an item only once the iteration
#    reaches the item.
#
# Under these rules, every combinator is cheap to construct eagerly, and we can
# stop the iteration at any point without having iterated over the rest.

#: Define the iterator over no instances.
_EMPTY = [
    Stripped(
        f"""\
/**
 * Iterate over no instances at all.
 */
class EmptyIterator : public impl::IIterator {{
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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}throw std::logic_error(
{III}"You want to get an instance from an EmptyIterator, but it is always done."
{II});
{I}}}

{I}void AppendToPath(Path&) const override {{
{II}throw std::logic_error(
{III}"You want to append the path of an EmptyIterator, but it is always done."
{II});
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<EmptyIterator>(*this);
{I}}}
}};  // class EmptyIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<impl::IIterator> Empty() {{
{I}return common::make_unique<EmptyIterator>();
}}"""
    ),
]  # type: Final[Sequence[Stripped]]


#: Define the iterator over a single instance.
_ONE = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over a single instance.
 *
 * We keep a copy of the shared pointer, upcast to types::IClass, so that
 * \\ref Get can return a reference to it.
 */
class OneIterator : public impl::IIterator {{
 public:
{I}explicit OneIterator(
{II}std::shared_ptr<types::IClass> instance
{I}) :
{II}instance_(std::move(instance)),
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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}return instance_;
{I}}}

{I}void AppendToPath(Path&) const override {{
{II}// Intentionally empty, as the instance itself is the end of the path.
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<OneIterator>(*this);
{I}}}

 private:
{I}std::shared_ptr<types::IClass> instance_;
{I}bool done_;
}};  // class OneIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<impl::IIterator> One(
{I}std::shared_ptr<types::IClass> instance
) {{
{I}return common::make_unique<OneIterator>(std::move(instance));
}}"""
    ),
]  # type: Final[Sequence[Stripped]]


#: Define the iterator over the children, one after another.
_CHAIN = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the instances of the children, one child after another.
 *
 * A child is started only once the previous child is done.
 */
class ChainIterator : public impl::IIterator {{
 public:
{I}explicit ChainIterator(
{II}std::vector<std::unique_ptr<impl::IIterator> > children
{I}) :
{II}children_(std::move(children)),
{II}active_(0) {{
{II}// Intentionally empty.
{I}}}

{I}ChainIterator(const ChainIterator& other) :
{II}active_(other.active_) {{
{II}children_.reserve(other.children_.size());
{II}for (const std::unique_ptr<impl::IIterator>& child : other.children_) {{
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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}return children_[active_]->Get();
{I}}}

{I}void AppendToPath(Path& path) const override {{
{II}children_[active_]->AppendToPath(path);
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<ChainIterator>(*this);
{I}}}

 private:
{I}std::vector<std::unique_ptr<impl::IIterator> > children_;

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
{I}std::vector<std::unique_ptr<impl::IIterator> >&
) {{
{I}// Intentionally empty, as there are no more children to collect.
}}"""
    ),
    Stripped(
        f"""\
template<typename... Rest>
void CollectChildren(
{I}std::vector<std::unique_ptr<impl::IIterator> >& children,
{I}std::unique_ptr<impl::IIterator> first,
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
std::unique_ptr<impl::IIterator> Chain(
{I}Children... children
) {{
{I}std::vector<std::unique_ptr<impl::IIterator> > collected;
{I}collected.reserve(sizeof...(Children));
{I}CollectChildren(collected, std::move(children)...);

{I}return common::make_unique<ChainIterator>(std::move(collected));
}}"""
    ),
]  # type: Final[Sequence[Stripped]]


#: Define the iterator over the instances in a property.
_IN_PROPERTY = [
    Stripped(
        f"""\
/**
 * Iterate over the instances of the \\p child, which lives in a property.
 */
class InPropertyIterator : public impl::IIterator {{
 public:
{I}InPropertyIterator(
{II}Property property,
{II}std::unique_ptr<impl::IIterator> child
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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}return child_->Get();
{I}}}

{I}void AppendToPath(Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<PropertySegment>(property_)
{II});
{II}child_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<InPropertyIterator>(*this);
{I}}}

 private:
{I}Property property_;
{I}std::unique_ptr<impl::IIterator> child_;
}};  // class InPropertyIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<impl::IIterator> InProperty(
{I}Property property,
{I}std::unique_ptr<impl::IIterator> child
) {{
{I}return common::make_unique<InPropertyIterator>(property, std::move(child));
}}"""
    ),
]  # type: Final[Sequence[Stripped]]


#: Define the iterator over the instances in a component of a tuple.
_AT_INDEX = [
    Stripped(
        f"""\
/**
 * Iterate over the instances of the \\p child, which lives in a component of a tuple.
 */
class AtIndexIterator : public impl::IIterator {{
 public:
{I}AtIndexIterator(
{II}std::size_t index,
{II}std::unique_ptr<impl::IIterator> child
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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}return child_->Get();
{I}}}

{I}void AppendToPath(Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<IndexSegment>(index_)
{II});
{II}child_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<AtIndexIterator>(*this);
{I}}}

 private:
{I}std::size_t index_;
{I}std::unique_ptr<impl::IIterator> child_;
}};  // class AtIndexIterator"""
    ),
    Stripped(
        f"""\
std::unique_ptr<impl::IIterator> AtIndex(
{I}std::size_t index,
{I}std::unique_ptr<impl::IIterator> child
) {{
{I}return common::make_unique<AtIndexIterator>(index, std::move(child));
}}"""
    ),
]  # type: Final[Sequence[Stripped]]


#: Define the iterator over the items of a list.
_EACH = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the instances of every item of a list, one item after another.
 *
 * The iterator over an item is built only once the iteration reaches the item.
 */
template<typename T>
class EachIterator : public impl::IIterator {{
 public:
{I}/**
{I} * Build the iterator over the instances of an item
{I} */
{I}typedef std::unique_ptr<impl::IIterator> (*OverItem)(
{II}const T& item,
{II}bool recursive
{I});

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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}return item_->Get();
{I}}}

{I}void AppendToPath(Path& path) const override {{
{II}path.segments.emplace_back(
{III}common::make_unique<IndexSegment>(index_)
{II});
{II}item_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
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
{I}std::unique_ptr<impl::IIterator> item_;

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
std::unique_ptr<impl::IIterator> Each(
{I}const std::vector<T>& items,
{I}std::unique_ptr<impl::IIterator> (*over_item)(const T& item, bool recursive),
{I}bool recursive
) {{
{I}return common::make_unique<EachIterator<T> >(&items, over_item, recursive);
}}"""
    ),
]  # type: Final[Sequence[Stripped]]


#: Define the iterator over an instance, and then over the instances it references.
_ONE_THEN_OVER = [
    Stripped(
        f"""\
/**
 * \\brief Iterate over the instances referenced from an instance, dispatched on
 * its runtime type.
 *
 * Defined below, once all the classes have been covered.
 */
std::unique_ptr<impl::IIterator> DispatchOnModelType(
{I}const types::IClass& instance,
{I}bool recursive
);"""
    ),
    Stripped(
        f"""\
/**
 * \\brief Iterate recursively over the instances referenced from an instance.
 *
 * We dispatch on the runtime type of the instance only in \\ref Start so that
 * we descend into the instance only once the iteration reaches it.
 */
class DispatchingIterator : public impl::IIterator {{
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

{I}const std::shared_ptr<types::IClass>& Get() const override {{
{II}return child_->Get();
{I}}}

{I}void AppendToPath(Path& path) const override {{
{II}child_->AppendToPath(path);
{I}}}

{I}std::unique_ptr<impl::IIterator> Clone() const override {{
{II}return common::make_unique<DispatchingIterator>(*this);
{I}}}

 private:
{I}const types::IClass* instance_;
{I}std::unique_ptr<impl::IIterator> child_;
}};  // class DispatchingIterator"""
    ),
    Stripped(
        f"""\
/**
 * Iterate over the instances referenced from the \\p instance, if \\p recursive.
 */
std::unique_ptr<impl::IIterator> Over(
{I}const types::IClass& instance,
{I}bool recursive
) {{
{I}if (!recursive) {{
{II}// NOTE (mristin):
{II}// In the non-recursive mode, we iterate only over the instances referenced
{II}// directly, but not over the instances which they reference in turn.
{II}return Empty();
{I}}}

{I}return common::make_unique<DispatchingIterator>(&instance);
}}"""
    ),
    Stripped(
        f"""\
/**
 * Iterate over the \\p instance, and then over the instances that it references.
 */
template<typename T>
std::unique_ptr<impl::IIterator> OneThenOver(
{I}const std::shared_ptr<T>& instance,
{I}bool recursive
) {{
{I}return Chain(One(instance), Over(*instance, recursive));
}}"""
    ),
]  # type: Final[Sequence[Stripped]]

# endregion Combinators

# region Iteration over the instances


def _yields(type_annotation: intermediate.TypeAnnotationUnion) -> bool:
    """Check whether a value of ``type_annotation`` references any instances."""
    if isinstance(type_annotation, intermediate.PrimitiveTypeAnnotation):
        return False

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation):
        return isinstance(
            type_annotation.our_type, (intermediate.Class, intermediate.NamedUnion)
        )

    elif isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        return _yields(type_annotation.value)

    elif isinstance(type_annotation, intermediate.ListTypeAnnotation):
        return _yields(type_annotation.items)

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        return any(_yields(item) for item in type_annotation.items)

    elif isinstance(
        type_annotation,
        (
            intermediate.JsonValueTypeAnnotation,
            intermediate.JsonArrayTypeAnnotation,
            intermediate.JsonObjectTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # A JSON-able value is plain data (``nlohmann::json``), never
        # a reference to one of our own classes.
        return False

    else:
        assert_never(type_annotation)

    raise AssertionError("Unexpected execution path")


def _yielding_classes(
    symbol_table: intermediate.SymbolTable,
) -> List[intermediate.ConcreteClass]:
    """List the concrete classes whose instances reference any other instances."""
    return [
        cls
        for cls in symbol_table.concrete_classes
        if any(_yields(prop.type_annotation) for prop in cls.properties)
    ]


# fmt: off
@require(
    lambda type_annotation, function_name_set:
    all(
        cpp_over.over_function_name(referenced) in function_name_set
        for referenced in cpp_over.referenced_function_types(type_annotation, _yields)
    ),
    "The functions over the referenced types have been collected"
)
@ensure(
    lambda function_name_set, result:
    result is None
    or cpp_over.called_function_names(result, defined="").issubset(
        function_name_set
    ),
    "The expression calls only the collected functions"
)
# fmt: on
def _generate_over_expression(
    type_annotation: intermediate.TypeAnnotationUnion,
    expr: str,
    function_name_set: AbstractSet[str],
) -> Optional[Stripped]:
    """
    Generate the iterator over the instances in ``expr`` of ``type_annotation``.

    The ``expr`` is the C++ expression of the value, for example:

    * ``that.semantic_id()`` for a property of the class (``that`` is the instance),
    * ``(*that.semantic_id())`` for the value of an optional property,
    * ``std::get<1>(value)`` for a component of a tuple, and
    * ``value`` for an item of a list.

    For example, we generate for a property ``semantic_id: Optional[Reference]``:

    .. code-block:: cpp

        that.semantic_id().has_value()
          ? OneThenOver((*that.semantic_id()), recursive)
          : Empty()

    and for a property ``keys: List[Key]``:

    .. code-block:: cpp

        Over_listOf_Key(that.keys(), recursive)

    The ``function_name_set`` contains the names of the collected functions over
    the lists, tuples and named unions, see
    :py:func:`cpp_over.collect_function_types`.

    Return ``None`` if a value of the ``type_annotation`` references no instances.
    """
    if not _yields(type_annotation):
        return None

    if isinstance(type_annotation, intermediate.OptionalTypeAnnotation):
        inner = _generate_over_expression(
            type_annotation=type_annotation.value,
            expr=f"(*{expr})",
            function_name_set=function_name_set,
        )
        assert inner is not None

        return Stripped(
            f"""\
{expr}.has_value()
{I}? {indent_but_first_line(inner, II)}
{I}: Empty()"""
        )

    elif isinstance(type_annotation, intermediate.OurTypeAnnotation) and isinstance(
        type_annotation.our_type, intermediate.Class
    ):
        return cpp_over.generate_call("OneThenOver", [expr, "recursive"])

    elif isinstance(
        type_annotation,
        (
            intermediate.OurTypeAnnotation,
            intermediate.ListTypeAnnotation,
            intermediate.TupleTypeAnnotation,
        ),
    ):
        # NOTE (mristin):
        # The other types of ours reference no instances, so this must be
        # a named union here.
        return cpp_over.generate_call(
            cpp_over.over_function_name(type_annotation), [expr, "recursive"]
        )

    else:
        raise AssertionError(
            f"Unexpected type annotation which references instances: "
            f"{type_annotation}"
        )


# fmt: off
@require(
    lambda type_annotation, function_name_set:
    cpp_over.over_function_name(type_annotation) in function_name_set,
    "The function over the type has been collected"
)
@require(
    lambda type_annotation, function_name_set:
    all(
        cpp_over.over_function_name(called) in function_name_set
        for called in cpp_over.called_function_types(type_annotation, _yields)
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
    function_name_set: AbstractSet[str],
) -> Tuple[Optional[Stripped], Stripped]:
    """
    Generate the function over the instances in a value of ``type_annotation``.

    For example, we generate for ``List[Key]`` the alias and the function:

    .. code-block:: cpp

        using listOf_Key = std::vector<
          std::shared_ptr<types::IKey>
        >;

        std::unique_ptr<impl::IIterator> Over_listOf_Key(
          const listOf_Key& value,
          bool recursive
        ) {
          return Each(value, &OneThenOver<types::IKey>, recursive);
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
            item_function = f"OneThenOver<types::{interface_name}>"
        else:
            item_function = cpp_over.over_function_name(items)

        body = Stripped(
            f"return "
            f"{cpp_over.generate_call('Each', ['value', f'&{item_function}', 'recursive'])};"
        )

    elif isinstance(type_annotation, intermediate.TupleTypeAnnotation):
        components = []  # type: List[Stripped]
        for i, item in enumerate(type_annotation.items):
            item_expression = _generate_over_expression(
                type_annotation=item,
                expr=f"std::get<{i}>(value)",
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
        # The alternatives of the variant follow the implementers, see
        # :py:func:`cpp_common.generate_named_union_variant_definition`.
        case_blocks = [
            Stripped(
                f"""\
case {i}:
{I}return OneThenOver(common::get<{i}>(value), recursive);"""
            )
            for i in range(len(named_union.implementers))
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
            function_name_set=function_name_set,
        )
        assert expression is not None
        body = Stripped(f"return {expression};")

    alias = None  # type: Optional[Stripped]

    if isinstance(
        type_annotation,
        (intermediate.ListTypeAnnotation, intermediate.TupleTypeAnnotation),
    ):
        alias_name = cpp_over.moniker(type_annotation)
        alias = Stripped(f"using {alias_name} = {value_type};")
        value_type = Stripped(alias_name)

    function = Stripped(
        f"""\
std::unique_ptr<impl::IIterator> {name}(
{I}const {indent_but_first_line(value_type, I)}& value,
{I}{cpp_over.generate_recursive_parameter(body)}
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )

    return alias, function


# fmt: off
@require(
    lambda cls:
    any(_yields(prop.type_annotation) for prop in cls.properties),
    "The instances of the class reference other instances"
)
@require(
    lambda cls, function_name_set:
    all(
        cpp_over.over_function_name(referenced) in function_name_set
        for prop in cls.properties
        for referenced in cpp_over.referenced_function_types(
            prop.type_annotation, _yields
        )
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
    function_name_set: AbstractSet[str],
) -> Stripped:
    """
    Generate the function over the instances referenced from an instance of ``cls``.

    For example, we generate for a class ``Reference`` with the properties
    ``referred_semantic_id: Optional[Reference]`` and ``keys: List[Key]``:

    .. code-block:: cpp

        std::unique_ptr<impl::IIterator> Over_Reference(
          const types::IReference& that,
          bool recursive
        ) {
          return Chain(
            InProperty(
              Property::kReferredSemanticId,
              that.referred_semantic_id().has_value()
                ? OneThenOver((*that.referred_semantic_id()), recursive)
                : Empty()
            ),
            InProperty(
              Property::kKeys,
              Over_listOf_Key(that.keys(), recursive)
            )
          );
        }

    The ``function_name_set`` contains the names of the collected functions, see
    :py:func:`cpp_over.collect_function_types`.
    """
    parts = []  # type: List[Stripped]

    for prop in cls.properties:
        expression = _generate_over_expression(
            type_annotation=prop.type_annotation,
            expr=f"that.{cpp_naming.getter_name(prop.name)}()",
            function_name_set=function_name_set,
        )
        if expression is None:
            continue

        property_literal = cpp_naming.enum_literal_name(prop.name)
        parts.append(
            cpp_over.generate_call(
                "InProperty", [f"Property::{property_literal}", expression]
            )
        )

    assert len(parts) > 0, "Otherwise the class would reference no instances"

    body = (
        Stripped(f"return {parts[0]};")
        if len(parts) == 1
        else Stripped(f"return {cpp_over.generate_call('Chain', parts)};")
    )

    interface_name = cpp_naming.interface_name(cls.name)
    name = cpp_over.over_class_function_name(cls)

    return Stripped(
        f"""\
std::unique_ptr<impl::IIterator> {name}(
{I}const types::{interface_name}& that,
{I}{cpp_over.generate_recursive_parameter(body)}
) {{
{I}{indent_but_first_line(body, I)}
}}"""
    )


def _generate_dispatch_on_model_type(
    yielding_classes: Sequence[intermediate.ConcreteClass],
) -> Stripped:
    """Generate the dispatch over the referenced instances on the runtime type."""
    doc_comment = Stripped(
        """\
/**
 * \\brief Iterate over the instances referenced from the \\p instance,
 * dispatched on its runtime type.
 *
 * If \\p recursive, we iterate also over the instances which the referenced
 * instances reference in turn.
 */"""
    )

    if len(yielding_classes) == 0:
        return Stripped(
            f"""\
{doc_comment}
std::unique_ptr<impl::IIterator> DispatchOnModelType(
{I}const types::IClass&,
{I}bool
) {{
{I}// NOTE (mristin):
{I}// The instances of no class reference any other instances.
{I}return Empty();
}}"""
        )

    case_blocks = []  # type: List[Stripped]
    for cls in yielding_classes:
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

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}// NOTE (mristin):
{I}// The instances of the other classes reference no other instances.
{I}return Empty();"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
{doc_comment}
std::unique_ptr<impl::IIterator> DispatchOnModelType(
{I}const types::IClass& instance,
{I}bool recursive
) {{
{I}switch (instance.model_type()) {{
{II}{indent_but_first_line(case_blocks_joined, II)}
{I}}}
}}"""
    )


def _is_used(function: str, code: str) -> bool:
    """Check whether the generated ``code`` calls or refers to the ``function``."""
    return re.search(rf"\b{function}\b", code) is not None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _generate_iteration_over_instances(
    symbol_table: intermediate.SymbolTable,
) -> Tuple[Optional[List[Stripped]], Optional[List[Error]]]:
    """Generate the combinators and the functions over the referenced instances."""
    yielding_classes = _yielding_classes(symbol_table=symbol_table)

    # NOTE (mristin):
    # We first collect the lists, tuples and named unions which need a function,
    # and only then generate the functions, so that the generation itself has no
    # state to keep.
    function_types, collection_errors = cpp_over.collect_function_types(
        classes=yielding_classes, yields=_yields
    )
    if collection_errors is not None:
        return None, collection_errors

    assert function_types is not None

    function_name_set = frozenset(
        cpp_over.over_function_name(function_type) for function_type in function_types
    )

    aliases_and_functions = [
        _generate_over_function(
            type_annotation=function_type, function_name_set=function_name_set
        )
        for function_type in function_types
    ]

    generated = [
        *(alias for alias, _ in aliases_and_functions if alias is not None),
        *(function for _, function in aliases_and_functions),
        *(
            _generate_over_class(cls=cls, function_name_set=function_name_set)
            for cls in yielding_classes
        ),
        _generate_dispatch_on_model_type(yielding_classes=yielding_classes),
    ]  # type: List[Stripped]

    generated_code = "\n".join(generated)

    # NOTE (mristin):
    # We include only the combinators which we use, as the compilers warn about
    # the unused functions.
    combinators = [*_EMPTY]
    for function, combinator in (
        ("Chain", _CHAIN),
        ("InProperty", _IN_PROPERTY),
        ("AtIndex", _AT_INDEX),
        ("Each", _EACH),
    ):
        if _is_used(function, generated_code):
            combinators.extend(combinator)

    if _is_used("OneThenOver", generated_code):
        # NOTE (mristin):
        # ``OneThenOver`` is a chain of ``One`` and ``Over``.
        if _CHAIN[0] not in combinators:
            combinators.extend(_CHAIN)

        combinators.extend(_ONE)
        combinators.extend(_ONE_THEN_OVER)

    return [*combinators, *generated], None


# endregion Iteration over the instances

# region Facade


def _generate_iterator_implementation() -> List[Stripped]:
    """Generate the impl. of the facade ``Iterator`` around ``impl::Iterator``."""
    return [
        Stripped(
            f"""\
Iterator::Iterator(
{I}const Iterator& other
) :
{I}implementation_(other.implementation_->Clone()),
{I}index_(other.index_) {{
{I}// Intentionally empty.
}}"""
        ),
        Stripped(
            f"""\
Iterator::Iterator(
{I}Iterator&& other
) :
{I}implementation_(std::move(other.implementation_)),
{I}index_(other.index_) {{
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
{II}implementation_ = std::move(other.implementation_);
{II}index_ = other.index_;
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
{I}index_ = implementation_->Done() ? -1 : index_ + 1;
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
{I}return a.index_ == b.index_;
}}"""
        ),
        Stripped(
            f"""\
bool operator!=(const Iterator& a, const Iterator& b) {{
{I}return a.index_ != b.index_;
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
{I}iterator.implementation_->AppendToPath(path);
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

{I}Path prefix;
{I}iterator.implementation_->AppendToPath(prefix);

{I}for (
{II}auto it = prefix.segments.rbegin();
{II}it != prefix.segments.rend();
{II}++it
{I}) {{
{II}path->segments.emplace_front(std::move(*it));
{I}}}
}}"""
        ),
    ]


def _generate_descent_and_descent_once_implementations() -> List[Stripped]:
    """Generate the implementation of the descent iterables."""
    blocks = []  # type: List[Stripped]

    for descent, recursive in (("Descent", "true"), ("DescentOnce", "false")):
        blocks.append(
            Stripped(
                f"""\
// region {descent}

// NOTE (mristin):
// We have to make a copy of the pointer since we would lose otherwise
// in range-based `for` loops,
// see: https://stackoverflow.com/questions/29990045/temporary-lifetime-in-range-for-expression
{descent}::{descent}(
{I}std::shared_ptr<types::IClass> instance
) : instance_(std::move(instance)) {{
{I}// Intentionally empty.
}}

Iterator {descent}::begin() const {{
{I}std::unique_ptr<impl::IIterator> it_impl(
{II}DispatchOnModelType(*instance_, {recursive})
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

const Iterator& {descent}::end() const {{
{I}static Iterator iterator(Empty());
{I}return iterator;
}}

// endregion {descent}"""
            )
        )

    return blocks


# endregion Facade


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
        *_generate_key_segment_implementation(),
        *_generate_path_implementation(),
        Stripped("// endregion Pathing"),
    ]  # type: List[Stripped]

    iteration_blocks, errors = _generate_iteration_over_instances(
        symbol_table=symbol_table
    )
    if errors is not None:
        return None, errors

    assert iteration_blocks is not None

    blocks.extend(
        [
            Stripped("namespace {"),
            Stripped("// region Iteration over the instances"),
            *iteration_blocks,
            Stripped("// endregion Iteration over the instances"),
            Stripped("}  // namespace"),
            Stripped("// region Iterator facade"),
            *_generate_iterator_implementation(),
            Stripped("// endregion Iterator facade"),
            Stripped("// region Descents"),
            *_generate_descent_and_descent_once_implementations(),
            Stripped("// endregion Descents"),
        ]
    )

    if len(symbol_table.enumerations) > 0:
        blocks.append(Stripped("// region Over enumerations"))

        for enum in symbol_table.enumerations:
            blocks.append(_generate_over_enum_implementation(enum))

        blocks.append(Stripped("// endregion Over enumerations"))

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
