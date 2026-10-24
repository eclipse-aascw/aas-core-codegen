import textwrap
import unittest
from typing import Dict, Final, Optional

from aas_core_codegen.common import Identifier, Stripped
import aas_core_codegen.java.common as java_common

import tests.common


class TestStringLiteral(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual('""', java_common.string_literal(""))

    def test_no_quotes(self) -> None:
        self.assertEqual('"x"', java_common.string_literal("x"))

    def test_tab(self) -> None:
        self.assertEqual('"a\\tb"', java_common.string_literal("a\tb"))


_SOURCE: Final[str] = textwrap.dedent(
    """\
    from enum import Enum


    class Some_enum(Enum):
        Some_literal = "some-literal"


    class Positive(int):
        pass


    @serialization(with_model_type=True)
    class Some_class:
        pass


    @serialization(with_model_type=True)
    class Another_class:
        pass


    Some_union = Union[Some_class, Another_class]


    class Something:
        some_str: str
        some_enum: Some_enum
        some_positive: Positive
        some_class: Some_class
        some_union: Some_union
        some_list: List[Some_class]
        some_set: Set[Some_enum]
        some_tuple: Tuple[str, Some_class]
        some_optional: Optional[List[Some_class]]
        some_json_value: JSONValue
        some_json_array: JSONArray
        some_json_object: JSONObject[str]

        def __init__(
            self,
            some_str: str,
            some_enum: Some_enum,
            some_positive: Positive,
            some_class: Some_class,
            some_union: Some_union,
            some_list: List[Some_class],
            some_set: Set[Some_enum],
            some_tuple: Tuple[str, Some_class],
            some_json_value: JSONValue,
            some_json_array: JSONArray,
            some_json_object: JSONObject[str],
            some_optional: Optional[List[Some_class]] = None,
        ) -> None:
            self.some_str = some_str
            self.some_enum = some_enum
            self.some_positive = some_positive
            self.some_class = some_class
            self.some_union = some_union
            self.some_list = some_list
            self.some_set = some_set
            self.some_tuple = some_tuple
            self.some_optional = some_optional
            self.some_json_value = some_json_value
            self.some_json_array = some_json_array
            self.some_json_object = some_json_object


    __version__ = "dummy"
    __xml_namespace__ = "https://dummy.com"
    """
)


def _generate_type_by_property(
    our_type_qualifier: Optional[Stripped],
) -> Dict[Identifier, Stripped]:
    """Generate the Java type for each property of ``Something`` in :py:data:`_SOURCE`."""
    symbol_table = tests.common.must_translate_source_to_intermediate(source=_SOURCE)

    something = symbol_table.must_find_class(Identifier("Something"))

    return {
        prop.name: java_common.generate_type(
            type_annotation=prop.type_annotation,
            our_type_qualifier=our_type_qualifier,
        )
        for prop in something.properties
    }


class TestGenerateType(unittest.TestCase):
    def test_without_qualifier(self) -> None:
        self.assertDictEqual(
            {
                "some_str": "String",
                "some_enum": "SomeEnum",
                "some_positive": "Long",
                "some_class": "ISomeClass",
                "some_union": "SomeUnion",
                "some_list": "List<ISomeClass>",
                "some_set": "Set<SomeEnum>",
                "some_tuple": "Tuple2<String, ISomeClass>",
                "some_optional": "Optional<List<ISomeClass>>",
                "some_json_value": "JsonNode",
                "some_json_array": "ArrayNode",
                "some_json_object": "ObjectNode",
            },
            _generate_type_by_property(our_type_qualifier=None),
        )

    def test_with_qualifier(self) -> None:
        # NOTE (mristin):
        # The qualifier applies only to our types, but not to the primitives,
        # the constrained primitives, the tuples themselves or the JSON-able values.
        self.assertDictEqual(
            {
                "some_str": "String",
                "some_enum": "types.SomeEnum",
                "some_positive": "Long",
                "some_class": "types.ISomeClass",
                "some_union": "types.SomeUnion",
                "some_list": "List<types.ISomeClass>",
                "some_set": "Set<types.SomeEnum>",
                "some_tuple": "Tuple2<String, types.ISomeClass>",
                "some_optional": "Optional<List<types.ISomeClass>>",
                "some_json_value": "JsonNode",
                "some_json_array": "ArrayNode",
                "some_json_object": "ObjectNode",
            },
            _generate_type_by_property(our_type_qualifier=Stripped("types")),
        )


if __name__ == "__main__":
    unittest.main()
