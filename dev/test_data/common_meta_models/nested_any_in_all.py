from typing import List, Optional

from icontract import DBC, invariant

from aas_core_meta.marker import abstract, serialization, verification


# region Verification functions


@verification
def is_english(language: str) -> bool:
    """Check that :paramref:`language` denotes English."""
    return language == "en"


@verification
def lang_string_sets_have_english(lang_string_sets: List["Lang_string_set"]) -> bool:
    """
    Check that every set in :paramref:`lang_string_sets` has at least one
    string in English.

    This function tests a plain ``any`` nested in ``all``.
    """
    return all(
        any(
            is_english(lang_string.language)
            for lang_string in lang_string_set.lang_strings
        )
        for lang_string_set in lang_string_sets
    )


@verification
def iec_contents_have_definition_in_english(
    specifications: List["Specification"],
) -> bool:
    """
    Check that the :attr:`Iec_content.definition` is defined at least in English
    for all the specifications whose content is an :class:`Iec_content`.

    This function tests an ``any`` nested in ``all``, where the nested ``any``
    iterates over an optional property of a value narrowed by ``isinstance``.
    """
    return all(
        not isinstance(specification.content, Iec_content)
        or (
            specification.content.definition is not None
            and any(
                is_english(lang_string.language)
                for lang_string in specification.content.definition
            )
        )
        for specification in specifications
    )


# endregion


class Lang_string(DBC):
    language: str
    text: str

    def __init__(self, language: str, text: str) -> None:
        self.language = language
        self.text = text


class Lang_string_set(DBC):
    lang_strings: List[Lang_string]

    def __init__(self, lang_strings: List[Lang_string]) -> None:
        self.lang_strings = lang_strings


@abstract
@serialization(with_model_type=True)
class Content(DBC):
    pass


class Iec_content(Content, DBC):
    definition: Optional[List[Lang_string]]

    def __init__(self, definition: Optional[List[Lang_string]] = None) -> None:
        self.definition = definition


class Other_content(Content, DBC):
    pass


class Specification(DBC):
    content: Content

    def __init__(self, content: Content) -> None:
        self.content = content


# fmt: off
@invariant(
    lambda self:
    lang_string_sets_have_english(self.lang_string_sets),
    "Every language string set must have at least one string in English."
)
@invariant(
    lambda self:
    all(
        any(
            lang_string.language == self.default_language
            for lang_string in lang_string_set.lang_strings
        )
        for lang_string_set in self.lang_string_sets
    ),
    "Every language string set must have at least one string in "
    "the default language."
)
@invariant(
    lambda self:
    not (self.specifications is not None)
    or iec_contents_have_definition_in_english(self.specifications),
    "The IEC contents must have a definition at least in English."
)
# fmt: on
class Something(DBC):
    default_language: str
    lang_string_sets: List[Lang_string_set]
    specifications: Optional[List[Specification]]

    def __init__(
        self,
        default_language: str,
        lang_string_sets: List[Lang_string_set],
        specifications: Optional[List[Specification]] = None,
    ) -> None:
        self.default_language = default_language
        self.lang_string_sets = lang_string_sets
        self.specifications = specifications


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
