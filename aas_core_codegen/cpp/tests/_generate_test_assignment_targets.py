"""Generate code to test the assignments to the properties and the list items."""

from typing import Final, List, Sequence

from icontract import ensure, require

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, Stripped
from aas_core_codegen.cpp import common as cpp_common
from aas_core_codegen.cpp.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
)


# NOTE (mristin):
# In contrast to the other targets, we test these assignments in C++ by executing
# them. The other SDKs share the objects and the lists by reference, just as Python
# does, so that the generated code of the common meta-model, checked against
# the golden files and compiled, suffices. C++, however, copies the vectors by value.
# The aliasing analysis in :py:mod:`aas_core_codegen.cpp.aliasing` decides where
# the transpiled code references the vectors and where it copies them, and only
# executing the mutations shows that the references and the copies behave as in
# Python.

#: Verification functions of the meta-model
#: ``dev/test_data/common_meta_models/assignment_targets.py`` called in the tests
ASSIGNMENT_TARGET_VERIFICATION_NAMES: Final[Sequence[Identifier]] = [
    Identifier("set_text"),
    Identifier("set_maybe_text"),
    Identifier("copy_maybe_text_and_set_maybe_kind"),
    Identifier("set_text_through_alias"),
    Identifier("set_texts"),
    Identifier("set_first_and_last_text"),
    Identifier("set_text_through_list_alias"),
    Identifier("set_numbers"),
    Identifier("set_nested_text"),
    Identifier("replace_first_item"),
    Identifier("set_texts_in_loops"),
    Identifier("fill_texts_of_item"),
    Identifier("fill_texts_through_alias"),
    Identifier("fill_texts_of_argument"),
    Identifier("rename_all"),
    Identifier("set_first_texts_of_lists"),
    Identifier("set_first_texts_in_sibling_loops"),
    Identifier("text_copy_is_independent"),
    Identifier("number_copy_is_independent"),
    Identifier("set_maybe_texts"),
    Identifier("set_maybe_item"),
    Identifier("set_text_of_rebound_alias"),
    Identifier("first_text_through_alias_is"),
    Identifier("texts_are_not_empty"),
]


def defines_assignment_target_verifications(
    symbol_table: intermediate.SymbolTable,
) -> bool:
    """
    Check whether the meta-model defines the verification functions to be tested.

    The tests call the verification functions directly, as the invariants must not
    call the functions which mutate their arguments. Hence, we generate the tests
    only for the meta-model which defines them,
    see :py:attr:`ASSIGNMENT_TARGET_VERIFICATION_NAMES`.
    """
    return all(
        name in symbol_table.verification_functions_by_name
        for name in ASSIGNMENT_TARGET_VERIFICATION_NAMES
    )


# fmt: off
@require(
    lambda symbol_table:
    defines_assignment_target_verifications(symbol_table)
)
@ensure(
    lambda result:
    result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate_implementation(
    symbol_table: intermediate.SymbolTable, library_namespace: Stripped
) -> str:
    """
    Generate code to test the assignments to the properties and the list items.

    The tests call the verification functions of the meta-model
    ``dev/test_data/common_meta_models/assignment_targets.py``.
    """
    include_prefix_path = cpp_common.generate_include_prefix_path(library_namespace)

    blocks: List[Stripped] = [
        cpp_common.WARNING,
        Stripped(
            """\
/**
 * Test the assignments to the properties and to the items of the lists
 * in the verification functions.
 *
 * The meta-model is written in Python, so the assignments follow the Python
 * semantics: the objects and the lists are shared by reference, a negative
 * index counts from the end of the list, and a list is copied explicitly
 * with <code>list(...)</code> when stored.
 */"""
        ),
        Stripped(
            f"""\
#include "{include_prefix_path}/types.hpp"
#include "{include_prefix_path}/verification.hpp"

#pragma warning(push, 0)
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#pragma warning(pop)

#include <catch2/catch.hpp>

namespace our = {library_namespace};"""
        ),
        Stripped(
            f"""\
std::shared_ptr<our::types::IItem> NewItem(
{I}std::wstring text,
{I}std::vector<std::wstring> texts
) {{
{I}return std::make_shared<our::types::Item>(
{II}std::move(text),
{II}std::move(texts)
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetText") {{
{I}auto item = NewItem(L"a", {{L"b"}});
{I}our::verification::SetText(item, L"x");
{I}REQUIRE(item->text() == L"x");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetMaybeText") {{
{I}auto item = NewItem(L"a", {{}});
{I}our::verification::SetMaybeText(item, L"x");
{I}REQUIRE(item->maybe_text().has_value());
{I}REQUIRE(*(item->maybe_text()) == L"x");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test CopyMaybeTextAndSetMaybeKind") {{
{I}std::shared_ptr<our::types::IItem> item = std::make_shared<our::types::Item>(
{II}L"a",
{II}std::vector<std::wstring>(),
{II}std::wstring(L"old")
{I});
{I}auto other = NewItem(L"b", {{}});
{I}our::verification::CopyMaybeTextAndSetMaybeKind(item, other);
{I}REQUIRE(!item->maybe_text().has_value());
{I}REQUIRE(item->maybe_kind().has_value());
{I}REQUIRE(*(item->maybe_kind()) == our::types::Kind::kAlpha);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetTextThroughAlias") {{
{I}auto item = NewItem(L"a", {{}});
{I}our::verification::SetTextThroughAlias(item, L"x");
{I}REQUIRE(item->text() == L"x");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetTexts") {{
{I}auto item = NewItem(L"a", {{L"b"}});
{I}std::vector<std::wstring> texts{{L"x", L"y"}};
{I}our::verification::SetTexts(item, texts);

{I}// NOTE (mristin):
{I}// The stored list is a copy, so its changes do not affect the property.
{I}texts[0] = L"z";
{I}REQUIRE(item->texts() == std::vector<std::wstring>{{L"x", L"y"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetFirstAndLastText") {{
{I}auto item = NewItem(L"a", {{L"a", L"b", L"c"}});
{I}our::verification::SetFirstAndLastText(item, L"x");
{I}REQUIRE(item->texts() == std::vector<std::wstring>{{L"x", L"b", L"x"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetTextThroughListAlias") {{
{I}auto item = NewItem(L"a", {{L"a", L"b", L"c"}});
{I}our::verification::SetTextThroughListAlias(item, L"x");
{I}REQUIRE(item->texts() == std::vector<std::wstring>{{L"a", L"x", L"c"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetNumbers") {{
{I}std::vector<int64_t> numbers{{1, 2, 3, 4}};
{I}our::verification::SetNumbers(numbers, 10);
{I}REQUIRE(numbers == std::vector<int64_t>{{10, 2, 5, 4}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetNumbers with an index out of range") {{
{I}std::vector<int64_t> numbers{{1}};
{I}REQUIRE_THROWS_AS(
{II}our::verification::SetNumbers(numbers, 10),
{II}std::out_of_range
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetNestedText") {{
{I}std::vector<std::shared_ptr<our::types::IItem> > items{{
{II}NewItem(L"a", {{L"a", L"b"}}),
{II}NewItem(L"b", {{L"c"}})
{I}}};
{I}our::verification::SetNestedText(items, L"x");
{I}REQUIRE(items[0]->texts() == std::vector<std::wstring>{{L"a", L"x"}});
{I}REQUIRE(items[1]->text() == L"x");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test ReplaceFirstItem") {{
{I}std::vector<std::shared_ptr<our::types::IItem> > items{{
{II}NewItem(L"a", {{}}),
{II}NewItem(L"b", {{}})
{I}}};
{I}auto item = NewItem(L"c", {{}});
{I}our::verification::ReplaceFirstItem(items, item);
{I}REQUIRE(items[0] == item);
{I}REQUIRE(items.size() == 2);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetTextsInLoops") {{
{I}std::vector<std::shared_ptr<our::types::IItem> > items{{
{II}NewItem(L"a", {{L"a"}}),
{II}NewItem(L"b", {{L"b", L"c"}})
{I}}};
{I}our::verification::SetTextsInLoops(items, L"x");
{I}for (const auto& item : items) {{
{II}REQUIRE(item->text() == L"x");
{II}REQUIRE(item->texts()[0] == L"x");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test FillTextsOfItem") {{
{I}auto item = NewItem(L"a", {{L"a", L"b"}});
{I}REQUIRE(our::verification::FillTextsOfItem(item, L"x"));
{I}REQUIRE(item->texts() == std::vector<std::wstring>{{L"x", L"x"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test FillTextsThroughAlias") {{
{I}auto item = NewItem(L"a", {{L"a", L"b"}});
{I}REQUIRE(our::verification::FillTextsThroughAlias(item, L"x"));
{I}REQUIRE(item->texts() == std::vector<std::wstring>{{L"x", L"x"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test FillTextsOfArgument") {{
{I}std::vector<std::wstring> texts{{L"a", L"b"}};
{I}REQUIRE(our::verification::FillTextsOfArgument(texts, L"x"));
{I}REQUIRE(texts == std::vector<std::wstring>{{L"x", L"x"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test RenameAll") {{
{I}std::vector<std::shared_ptr<our::types::IItem> > items{{
{II}NewItem(L"a", {{}}),
{II}NewItem(L"b", {{}})
{I}}};
{I}REQUIRE(our::verification::RenameAll(items, L"x"));
{I}for (const auto& item : items) {{
{II}REQUIRE(item->text() == L"x");
{I}}}
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetFirstTextsOfLists") {{
{I}std::vector<std::vector<std::wstring> > lists{{
{II}{{L"a", L"b"}},
{II}{{L"c"}}
{I}}};
{I}our::verification::SetFirstTextsOfLists(lists, L"x");
{I}REQUIRE(lists[0] == std::vector<std::wstring>{{L"x", L"b"}});
{I}REQUIRE(lists[1] == std::vector<std::wstring>{{L"x"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetFirstTextsInSiblingLoops") {{
{I}std::vector<std::shared_ptr<our::types::IItem> > items{{
{II}NewItem(L"a", {{L"a"}})
{I}}};
{I}std::vector<std::shared_ptr<our::types::IItem> > others{{
{II}NewItem(L"b", {{L"b", L"c"}})
{I}}};
{I}our::verification::SetFirstTextsInSiblingLoops(items, others, L"x");
{I}REQUIRE(items[0]->texts() == std::vector<std::wstring>{{L"x"}});
{I}REQUIRE(others[0]->texts() == std::vector<std::wstring>{{L"x", L"c"}});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test TextCopyIsIndependent") {{
{I}auto item = NewItem(L"a", {{}});
{I}REQUIRE(our::verification::TextCopyIsIndependent(item, L"x"));
{I}REQUIRE(item->text() == L"x");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test NumberCopyIsIndependent") {{
{I}std::vector<int64_t> numbers{{1, 2}};
{I}REQUIRE(our::verification::NumberCopyIsIndependent(numbers));
{I}REQUIRE(numbers[0] == 2);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetMaybeTexts") {{
{I}auto item = NewItem(L"a", {{}});
{I}std::vector<std::wstring> texts{{L"x", L"y"}};
{I}our::verification::SetMaybeTexts(item, texts);

{I}// NOTE (mristin):
{I}// The stored list is a copy, so its changes do not affect the property.
{I}texts[0] = L"z";
{I}REQUIRE(item->maybe_texts().has_value());
{I}REQUIRE(
{II}*(item->maybe_texts()) == std::vector<std::wstring>{{L"x", L"y"}}
{I});
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetMaybeItem") {{
{I}std::shared_ptr<our::types::ISomething> something =
{II}std::make_shared<our::types::Something>(
{III}std::vector<std::shared_ptr<our::types::IItem> >()
{II});
{I}auto item = NewItem(L"a", {{}});
{I}our::verification::SetMaybeItem(something, item);
{I}REQUIRE(something->maybe_item().has_value());
{I}REQUIRE(*(something->maybe_item()) == item);
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test SetTextOfReboundAlias") {{
{I}auto item = NewItem(L"a", {{}});
{I}auto other = NewItem(L"b", {{}});
{I}our::verification::SetTextOfReboundAlias(item, other, L"x");
{I}REQUIRE(item->text() == L"a");
{I}REQUIRE(other->text() == L"x");
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test FirstTextThroughAliasIs") {{
{I}auto item = NewItem(L"a", {{L"x"}});
{I}REQUIRE(our::verification::FirstTextThroughAliasIs(item, L"x"));
{I}REQUIRE(!our::verification::FirstTextThroughAliasIs(item, L"y"));
}}"""
        ),
        Stripped(
            f"""\
TEST_CASE("Test TextsAreNotEmpty") {{
{I}std::vector<std::shared_ptr<our::types::IItem> > items{{
{II}NewItem(L"a", {{L"b"}})
{I}}};
{I}REQUIRE(our::verification::TextsAreNotEmpty(items));

{I}items.push_back(NewItem(L"c", {{L"d", L""}}));
{I}REQUIRE(!our::verification::TextsAreNotEmpty(items));
}}"""
        ),
        cpp_common.WARNING,
    ]

    return "\n\n".join(blocks) + "\n"


assert generate_implementation.__doc__ is not None
assert generate_implementation.__doc__.strip().startswith(__doc__.strip())
