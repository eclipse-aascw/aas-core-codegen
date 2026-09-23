# pylint: disable=missing-docstring

import unittest

from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier
from aas_core_codegen.intermediate import doc as intermediate_doc
import aas_core_codegen.cpp.common as cpp_common
import aas_core_codegen.cpp.description as cpp_description
import aas_core_codegen.csharp.description as csharp_description
import aas_core_codegen.golang.common as golang_common
import aas_core_codegen.golang.description as golang_description
import aas_core_codegen.java.common as java_common
import aas_core_codegen.java.description as java_description
import aas_core_codegen.python.common as python_common
import aas_core_codegen.python.description as python_description
import aas_core_codegen.typescript.common as typescript_common
import aas_core_codegen.typescript.description as typescript_description

import tests.common


class Test_reference_to_verification_function(unittest.TestCase):
    symbol_table: intermediate.SymbolTable
    element: intermediate_doc.ReferenceToVerificationFunction

    @classmethod
    def setUpClass(cls) -> None:
        source = '''\
@verification
def matches_something(text: str) -> bool:
    """Check that :paramref:`text` is something."""
    return match("^something$", text) is not None


class Something:
    """See :func:`matches_something`."""

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
'''

        symbol_table, error = tests.common.translate_source_to_intermediate(
            source=source
        )
        assert error is None, tests.common.most_underlying_messages(error)
        assert symbol_table is not None

        something = symbol_table.must_find_class(Identifier("Something"))
        assert something.description is not None

        elements = list(
            something.description.summary.findall(
                condition=intermediate_doc.ReferenceToVerificationFunction
            )
        )
        assert len(elements) == 1

        cls.symbol_table = symbol_table
        cls.element = elements[0]

    def test_cpp(self) -> None:
        # noinspection PyProtectedMember
        renderer = cpp_description._ElementRenderer(
            context=cpp_description.Context(
                namespace=cpp_common.TYPES_NAMESPACE, cls_or_enum=None
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual("verification::MatchesSomething", rendered)

        # noinspection PyProtectedMember
        renderer = cpp_description._ElementRenderer(
            context=cpp_description.Context(
                namespace=cpp_common.VERIFICATION_NAMESPACE, cls_or_enum=None
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual("MatchesSomething", rendered)

    def test_csharp(self) -> None:
        something = self.symbol_table.must_find_class(Identifier("Something"))
        assert something.description is not None

        code, errors = csharp_description.generate_comment_for_our_type(
            something.description
        )
        assert errors is None, tests.common.most_underlying_messages(errors)
        self.assertEqual(
            """\
/// <summary>
/// See <see cref="Aas.Verification.MatchesSomething" />.
/// </summary>""",
            code,
        )

    def test_golang(self) -> None:
        # noinspection PyProtectedMember
        renderer = golang_description._ElementRenderer(
            context=golang_description.Context(
                package=golang_common.TYPES_PACKAGE, cls_or_enum=None
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual(
            f"[{golang_common.VERIFICATION_PACKAGE}.MatchesSomething]", rendered
        )

        # noinspection PyProtectedMember
        renderer = golang_description._ElementRenderer(
            context=golang_description.Context(
                package=golang_common.VERIFICATION_PACKAGE, cls_or_enum=None
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual("[MatchesSomething]", rendered)

    def test_java(self) -> None:
        something = self.symbol_table.must_find_class(Identifier("Something"))
        assert something.description is not None

        code, errors = java_description.generate_comment_for_our_type(
            something.description,
            context=java_description.Context(
                package=java_common.PackageIdentifier("aas_core.aas3_0"),
                cls_or_enum=something,
            ),
        )
        assert errors is None, tests.common.most_underlying_messages(errors)
        assert code is not None
        self.assertIn(
            "{@link aas_core.aas3_0.verification.Verification#matchesSomething}",
            code,
        )

    def test_python(self) -> None:
        # noinspection PyProtectedMember
        renderer = python_description._ElementRenderer(
            context=python_description.Context(
                qualified_module_name=python_common.QualifiedModuleName("aas_core"),
                module=Identifier("types"),
                cls_or_enum=None,
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual(":py:func:`.verification.matches_something`", rendered)

        # noinspection PyProtectedMember
        renderer = python_description._ElementRenderer(
            context=python_description.Context(
                qualified_module_name=python_common.QualifiedModuleName("aas_core"),
                module=Identifier("verification"),
                cls_or_enum=None,
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual(":py:func:`matches_something`", rendered)

    def test_typescript(self) -> None:
        # noinspection PyProtectedMember
        renderer = typescript_description._ElementRenderer(
            context=typescript_description.Context(
                module=typescript_common.TYPES_MODULE, cls_or_enum=None
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual("{@link verification!matchesSomething}", rendered)

        # noinspection PyProtectedMember
        renderer = typescript_description._ElementRenderer(
            context=typescript_description.Context(
                module=typescript_common.VERIFICATION_MODULE, cls_or_enum=None
            )
        )
        rendered, errors = renderer.transform(self.element)
        assert errors is None, errors
        self.assertEqual("{@link matchesSomething}", rendered)


if __name__ == "__main__":
    unittest.main()
