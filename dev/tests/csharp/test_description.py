# pylint: disable=missing-docstring

import unittest.mock

# noinspection PyProtectedMember
import aas_core_codegen.csharp.description as csharp_description
import tests.common
from aas_core_codegen.common import Stripped, Identifier


class Test_to_render_description_of_meta_model(unittest.TestCase):
    @staticmethod
    def render(source: str) -> Stripped:
        """Generate the C# description comment based on ``source``."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        assert (
            symbol_table.meta_model.description is not None
        ), "Expected a meta-model description, but found none."

        code, errors = csharp_description.generate_comment_for_meta_model(
            symbol_table.meta_model.description
        )
        assert errors is None, tests.common.most_underlying_messages(errors)

        assert code is not None

        return code

    def test_empty_description_not_allowed(self) -> None:
        source = '''\
""""""  # Intentionally left empty

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = tests.common.translate_source_to_intermediate(source=source)
        assert error is not None
        self.assertEqual(
            "Unexpected empty description", tests.common.most_underlying_messages(error)
        )

    def test_only_summary(self) -> None:
        comment_code = self.__class__.render(
            '''\
"""Do & drink something."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink something.
/// </summary>""",
            comment_code,
        )


class Test_to_render_description_of_our_types(unittest.TestCase):
    @staticmethod
    def render(source: str) -> Stripped:
        """
        Generate the C# description comment based on ``source``.

        The ``source`` is expected to contain only a single class, a class
        ``Some_class``.
        """
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        something_type = symbol_table.must_find_our_type(Identifier("Something"))
        assert something_type.description is not None

        code, errors = csharp_description.generate_comment_for_our_type(
            something_type.description
        )
        assert errors is None, tests.common.most_underlying_messages(errors)

        assert code is not None

        return code

    def test_empty_description_not_allowed(self) -> None:
        source = '''\
class Some_class:
    """"""  # Intentionally left empty

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = tests.common.translate_source_to_intermediate(source=source)
        assert error is not None
        self.assertEqual(
            "Unexpected empty description", tests.common.most_underlying_messages(error)
        )

    def test_no_summary(self) -> None:
        source = '''\
class Some_class:
    """
    * Some
    * Bullet
    * List
    """

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = tests.common.translate_source_to_intermediate(source=source)

        assert error is not None

        self.assertEqual(
            "Expected the first document element to be a summary and thus a paragraph, "
            "but got: "
            '<bullet_list bullet="*">'
            "<list_item><paragraph>Some</paragraph></list_item>"
            "<list_item><paragraph>Bullet</paragraph></list_item>"
            "<list_item><paragraph>List</paragraph></list_item>"
            "</bullet_list>",
            tests.common.most_underlying_messages(error),
        )

    def test_unexpected_directive(self) -> None:
        source = '''\
class Some_class:
    """
    Do something.

    :someDirective:
        I am unexpected.
    """

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = tests.common.translate_source_to_intermediate(source=source)

        assert error is not None

        self.assertEqual(
            "Expected only directives such as ``constraint some-identifier`` "
            "in this context, but got a directive with 1 part(s): someDirective",
            tests.common.most_underlying_messages(error),
        )

    def test_only_summary(self) -> None:
        comment_code = Test_to_render_description_of_our_types.render(
            '''\
class Something:
    """Do & drink something."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink something.
/// </summary>""",
            comment_code,
        )

    def test_summary_with_class_reference(self) -> None:
        comment_code = Test_to_render_description_of_our_types.render(
            '''\
class Something:
    """Do & drink :class:`Something`."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink <see cref="Aas.Something" />.
/// </summary>""",
            comment_code,
        )

    def test_summary_with_interface_reference(self) -> None:
        comment_code = Test_to_render_description_of_our_types.render(
            '''\
@abstract
class Something:
    """Do & drink :class:`Something`."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink <see cref="Aas.ISomething" />.
/// </summary>""",
            comment_code,
        )

    def test_summary_with_enumeration_reference(self) -> None:
        comment_code = Test_to_render_description_of_our_types.render(
            '''\
class Something(Enum):
    """Do & drink :class:`Something`."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink <see cref="Aas.Something" />.
/// </summary>""",
            comment_code,
        )

    def test_summary_and_remarks(self) -> None:
        comment_code = Test_to_render_description_of_our_types.render(
            '''\
class Something:
    """
    Do & drink something.

    First & remark.

    Second & remark.
    """

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink something.
/// </summary>
/// <remarks>
/// <para>
/// First &amp; remark.
/// </para>
/// <para>
/// Second &amp; remark.
/// </para>
/// </remarks>""",
            comment_code,
        )

    def test_summary_remarks_and_constraints(self) -> None:
        comment_code = Test_to_render_description_of_our_types.render(
            # NOTE (mristin, 2022-07-21):
            # We explicitly test here for three cases:
            # 1) a single-paragraph constraint,
            # 2) a two-paragraph constraint, and
            # 3) a constraint with an unordered list.
            '''\
class Something:
    """
    Do & drink something.

    First & remark.

    :constraint AAS-001:
        You shall parse.

    :constraint AAS-002:
        You have to do something.

        Really.

    :constraint AAS-003:
        You shall:

        * Do something,
        * And do it now.
    """

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )
        self.assertEqual(
            """\
/// <summary>
/// Do &amp; drink something.
/// </summary>
/// <remarks>
/// <para>
/// First &amp; remark.
/// </para>
/// <para>
/// Constraints:
/// </para>
/// <ul>
///   <li>
///     Constraint AAS-001:
///     You shall parse.
///   </li>
///   <li>
///     <para>
///     Constraint AAS-002:
///     You have to do something.
///     </para>
///     <para>
///     Really.
///     </para>
///   </li>
///   <li>
///     <para>
///     Constraint AAS-003:
///     You shall:
///     </para>
///     <ul>
///       <li>
///         Do something,
///       </li>
///       <li>
///         And do it now.
///       </li>
///     </ul>
///   </li>
/// </ul>
/// </remarks>""",
            comment_code,
        )

    def test_summary_and_note_in_the_remarks(self) -> None:
        # NOTE (mristin, 2022-07-21):
        # This is a real-world example from aas-core-meta which is kept here as
        # a regression test as we did not render it correctly at first. There was
        # a ``<para>`` nested in the ``<remarks>`` element.
        comment_code = Test_to_render_description_of_our_types.render(
            '''\
class Something:
    """
    Global reference to the data specification template used by
    the element.

    .. note::

        This is a global reference.
    """

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Global reference to the data specification template used by
/// the element.
/// </summary>
/// <remarks>
/// This is a global reference.
/// </remarks>""",
            comment_code,
        )


class Test_to_render_description_of_signature(unittest.TestCase):
    @staticmethod
    def render(source: str) -> Stripped:
        """
        Generate the C# description comment based on ``source``.

        The ``source`` is expected to contain only a single verification function,
        ``verify_something``.
        """
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        verification = symbol_table.verification_functions_by_name[
            Identifier("verify_something")
        ]

        assert verification.description is not None

        code, errors = csharp_description.generate_comment_for_signature(
            verification.description
        )
        assert errors is None, tests.common.most_underlying_messages(errors)

        assert code is not None

        return code

    def test_empty_description_not_allowed(self) -> None:
        source = '''\
@verification
def verify_something(text: str) -> bool:
    """"""  # Intentionally left empty
    return match(r'.*', text) is not None

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        _, error = tests.common.translate_source_to_intermediate(source=source)

        assert error is not None

        self.assertEqual(
            "Unexpected empty description", tests.common.most_underlying_messages(error)
        )

    def test_only_summary(self) -> None:
        source = '''\
@verification
def verify_something(text: str) -> bool:
    """Verify something."""
    return match(r'^.*$', text) is not None

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        code = Test_to_render_description_of_signature.render(source=source)

        self.assertEqual(
            """\
/// <summary>
/// Verify something.
/// </summary>""",
            code,
        )

    def test_params_and_returns(self) -> None:
        # NOTE (mristin, 2022-07-21):
        # We explicitly check here for multiple paragraphs in the param and returns.
        source = '''\
@verification
def verify_something(first: str, second: str) -> bool:
    """
    Verify something.

    :param first: to be checked
    :param second:
        another thing to be checked.

        really to be checked.

    :returns:
        True if :paramref:`first` and :paramref:`second` are
        a valid something.

        Otherwise, return false.
    """
    return match(r'.*', text) is not None

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        code = Test_to_render_description_of_signature.render(source=source)

        self.assertEqual(
            """\
/// <summary>
/// Verify something.
/// </summary>
/// <param name="first">
/// to be checked
/// </param>
/// <param name="second">
/// <para>
/// another thing to be checked.
/// </para>
/// <para>
/// really to be checked.
/// </para>
/// </param>
/// <returns>
/// <para>
/// True if <paramref name="first" /> and <paramref name="second" /> are
/// a valid something.
/// </para>
/// <para>
/// Otherwise, return false.
/// </para>
/// </returns>""",
            code,
        )


class Test_to_render_paragraphs(unittest.TestCase):
    @staticmethod
    def render(source: str) -> Stripped:
        """Generate the C# description comment based on ``source``."""
        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        assert (
            symbol_table.meta_model.description is not None
        ), "Expected a meta-model description, but found none."

        code, errors = csharp_description.generate_comment_for_meta_model(
            symbol_table.meta_model.description
        )
        assert errors is None, tests.common.most_underlying_messages(errors)

        assert code is not None

        return code

    def test_single_paragraph(self) -> None:
        comment_code = self.__class__.render(
            '''\
"""Write a single paragraph."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// Write a single paragraph.
/// </summary>""",
            comment_code,
        )

    def test_multiple_text_remarks(self) -> None:
        comment_code = self.__class__.render(
            '''\
"""
This is summary.

This is first paragraph of remarks.

This is second paragraph of remarks.
"""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// This is summary.
/// </summary>
/// <remarks>
/// <para>
/// This is first paragraph of remarks.
/// </para>
/// <para>
/// This is second paragraph of remarks.
/// </para>
/// </remarks>""",
            comment_code,
        )

    def test_multiple_remarks_of_mixed_lists_and_text(self) -> None:
        comment_code = self.__class__.render(
            '''\
"""
This is summary.

This is first paragraph of remarks.

This is a list:

* First item
* Second item

This is the third paragraph.
"""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''
        )

        self.assertEqual(
            """\
/// <summary>
/// This is summary.
/// </summary>
/// <remarks>
/// <para>
/// This is first paragraph of remarks.
/// </para>
/// <para>
/// This is a list:
/// </para>
/// <ul>
///   <li>
///     First item
///   </li>
///   <li>
///     Second item
///   </li>
/// </ul>
/// <para>
/// This is the third paragraph.
/// </para>
/// </remarks>""",
            comment_code,
        )


if __name__ == "__main__":
    unittest.main()
