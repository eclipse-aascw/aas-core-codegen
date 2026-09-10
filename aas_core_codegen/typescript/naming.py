"""Generate TypeScript identifiers based on the identifiers from the meta-model."""
from typing import Union, Final, FrozenSet

from icontract import require

import aas_core_codegen.naming
from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, assert_never

# NOTE (mristin):
# This is the set of the *true* ECMAScript/TypeScript reserved words -- *i.e.*,
# words which can *never* be used as a binding identifier (a variable, a function
# or a parameter name), be it in ordinary or in strict mode code. Since every file
# that we generate is an ES module (it contains a top-level ``import``/``export``),
# it always runs in strict mode, so the words reserved only in strict mode are
# reserved for us as well.
#
# We downloaded this list from the MDN lexical grammar reference on 2026-08-28:
# https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Lexical_grammar
# (the "Keywords", "Future reserved words" and "Future reserved words in older
# standards" -- except the latter, since those are *not* enforced by any
# TypeScript version we tested, see below -- sections).
#
# We deliberately do *not* include the many TypeScript-specific *contextual*
# keywords (such as ``type``, ``as``, ``readonly``, ``namespace``, ``declare``,
# ``get``, ``set``, ``of``, ``from``, ``async``, ...) which the compiler only
# recognizes as keywords in a handful of specific positions. We cross-referenced
# the full list of tokens the compiler treats as keywords against
# ``textToKeywordObj`` in
# https://github.com/microsoft/TypeScript/blob/v5.6.3/src/compiler/scanner.ts,
# and verified with ``tsc --strict`` (TypeScript 5.6.3) that a contextual keyword
# such as ``type`` can indeed still be used as a variable, function or parameter
# name without any compiler error, whereas a *true* reserved word such as
# ``enum`` can not (*e.g.*, ``function enum(): void {}`` fails with
# "'enum' is a reserved word that cannot be used here.").
_KEYWORD_SET: Final[FrozenSet[Identifier]] = frozenset(
    [
        Identifier("await"),
        Identifier("break"),
        Identifier("case"),
        Identifier("catch"),
        Identifier("class"),
        Identifier("const"),
        Identifier("continue"),
        Identifier("debugger"),
        Identifier("default"),
        Identifier("delete"),
        Identifier("do"),
        Identifier("else"),
        Identifier("enum"),
        Identifier("export"),
        Identifier("extends"),
        Identifier("false"),
        Identifier("finally"),
        Identifier("for"),
        Identifier("function"),
        Identifier("if"),
        Identifier("implements"),
        Identifier("import"),
        Identifier("in"),
        Identifier("instanceof"),
        Identifier("interface"),
        Identifier("let"),
        Identifier("new"),
        Identifier("null"),
        Identifier("package"),
        Identifier("private"),
        Identifier("protected"),
        Identifier("public"),
        Identifier("return"),
        Identifier("static"),
        Identifier("super"),
        Identifier("switch"),
        Identifier("this"),
        Identifier("throw"),
        Identifier("true"),
        Identifier("try"),
        Identifier("typeof"),
        Identifier("var"),
        Identifier("void"),
        Identifier("while"),
        Identifier("with"),
        Identifier("yield"),
    ]
)

assert all(len(keyword) > 1 for keyword in _KEYWORD_SET), (
    f"We expect all the keywords to be at least 2 characters, "
    f"but we got at least one which is not: {_KEYWORD_SET=}."
    f"We built the naming logic based on this assumption since we uppercase the last "
    f"letter whenever the identifier conflicts with a keyword."
)

assert all(keyword.islower() for keyword in _KEYWORD_SET), (
    "We expected all the keywords to be lowercase, since that was the assumption "
    "when we renamed them to avoid conflicts, "
    f"but that is not the case: {_KEYWORD_SET=}"
)


@require(lambda keyword: keyword in _KEYWORD_SET)
def _transform_keyword_to_lowercase_with_upper_last_letter(
    keyword: Identifier,
) -> Identifier:
    """
    Transform the keyword identifier into a lowercase TypeScript identifier.

    >>> _transform_keyword_to_lowercase_with_upper_last_letter(Identifier("enum"))
    'enuM'
    """
    return Identifier(keyword[:-1] + keyword[-1].upper())


# NOTE (mristin):
# These are the names of the TypeScript utility types, which are declared globally
# (in ``lib.es5.d.ts`` *etc.*) and thus available, unqualified, in every TypeScript
# file. If we named a generated class or enum after one of them, we would shadow
# the utility type for the rest of that module -- which is a real problem here,
# since we ourselves use, *e.g.*, ``Readonly<Class>`` in the generated code (see
# ``_generate_type_matcher`` in ``_generate_types.py``), so shadowing a utility
# type with an unrelated, non-generic class or enum of the same name would break
# our own generated code.
#
# We downloaded this list from the TypeScript handbook on 2026-08-28:
# https://www.typescriptlang.org/docs/handbook/utility-types.html
# (the name of every utility type documented on that page, in the order in which
# they appear there).
_UTILITY_TYPE_SET: Final[FrozenSet[Identifier]] = frozenset(
    [
        Identifier("Awaited"),
        Identifier("Partial"),
        Identifier("Required"),
        Identifier("Readonly"),
        Identifier("Record"),
        Identifier("Pick"),
        Identifier("Omit"),
        Identifier("Exclude"),
        Identifier("Extract"),
        Identifier("NonNullable"),
        Identifier("Parameters"),
        Identifier("ConstructorParameters"),
        Identifier("ReturnType"),
        Identifier("InstanceType"),
        Identifier("NoInfer"),
        Identifier("ThisParameterType"),
        Identifier("OmitThisParameter"),
        Identifier("ThisType"),
        Identifier("Uppercase"),
        Identifier("Lowercase"),
        Identifier("Capitalize"),
        Identifier("Uncapitalize"),
    ]
)

assert all(len(name) > 1 for name in _UTILITY_TYPE_SET), (
    f"We expect all the utility type names to be at least 2 characters, "
    f"but we got at least one which is not: {_UTILITY_TYPE_SET=}. "
    f"We built the naming logic based on this assumption since we uppercase the "
    f"last letter whenever the identifier conflicts with a utility type."
)

assert all(name[0].isupper() for name in _UTILITY_TYPE_SET), (
    "We expected all the utility type names to start with an upper-case letter, "
    "since that was the assumption when we renamed the conflicting identifiers, "
    f"but that is not the case: {_UTILITY_TYPE_SET=}"
)


@require(lambda name: name in _UTILITY_TYPE_SET)
def _transform_utility_type_name_with_upper_last_letter(
    name: Identifier,
) -> Identifier:
    """
    Transform the utility type name into a distinct TypeScript identifier.

    >>> _transform_utility_type_name_with_upper_last_letter(Identifier("Partial"))
    'PartiaL'
    """
    return Identifier(name[:-1] + name[-1].upper())


# fmt: off
@require(
    lambda identifier: identifier[0].isupper(),
    "Enumeration name must start with a capital letter"
)
# fmt: on
def enum_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an enum based on its meta-model ``identifier``.

    If the name conflicts with a TypeScript utility type such as ``Partial``,
    it is translated as, *e.g.*, ``PartiaL``, to avoid conflicts.

    >>> enum_name(Identifier("Something"))
    'Something'

    >>> enum_name(Identifier("URL_to_something"))
    'UrlToSomething'

    >>> enum_name(Identifier("Something_to_URL"))
    'SomethingToUrl'

    >>> enum_name(Identifier("Partial"))
    'PartiaL'
    """
    name = aas_core_codegen.naming.capitalized_camel_case(identifier)
    if name in _UTILITY_TYPE_SET:
        return _transform_utility_type_name_with_upper_last_letter(name)

    return name


# fmt: off
@require(
    lambda identifier:
    identifier[0].isupper(),
    "Class names must start with a capital letter"
)
# fmt: on
def class_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a class based on its meta-model ``identifier``.

    If the name conflicts with a TypeScript utility type such as ``Partial``,
    it is translated as, *e.g.*, ``PartiaL``, to avoid conflicts.

    >>> class_name(Identifier("Something"))
    'Something'

    >>> class_name(Identifier("URL_to_something"))
    'UrlToSomething'

    >>> class_name(Identifier("Something_to_URL"))
    'SomethingToUrl'

    >>> class_name(Identifier("Partial"))
    'PartiaL'
    """
    name = aas_core_codegen.naming.capitalized_camel_case(identifier)
    if name in _UTILITY_TYPE_SET:
        return _transform_utility_type_name_with_upper_last_letter(name)

    return name


def union_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a named union based on its meta-model ``identifier``.

    A named union is represented as a type alias, so it follows the same
    convention as :py:func:`class_name`, but is kept as a separate function
    since a named union is conceptually distinct from a class.

    >>> union_name(Identifier("Something"))
    'Something'

    >>> union_name(Identifier("URL_to_something"))
    'UrlToSomething'

    >>> union_name(Identifier("Something_to_URL"))
    'SomethingToUrl'
    """
    name = aas_core_codegen.naming.capitalized_camel_case(identifier)
    if name in _UTILITY_TYPE_SET:
        return _transform_utility_type_name_with_upper_last_letter(name)

    return name


def name_of(
    something: Union[
        intermediate.Enumeration,
        intermediate.AbstractClass,
        intermediate.ConcreteClass,
        intermediate.NamedUnion,
    ]
) -> Identifier:
    """Dispatch the name based on the run-time type of ``something``."""
    if isinstance(something, intermediate.Enumeration):
        return enum_name(something.name)

    elif isinstance(
        something, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ):
        return class_name(something.name)

    elif isinstance(something, intermediate.NamedUnion):
        return union_name(something.name)

    else:
        assert_never(something)


def enum_literal_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an enum literal based on its meta-model ``identifier``.

    >>> enum_literal_name(Identifier("something"))
    'Something'

    >>> enum_literal_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def constant_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a constant based on its meta-model ``identifier``.

    >>> constant_name(Identifier("something"))
    'SOMETHING'

    >>> constant_name(Identifier("URL_to_something"))
    'URL_TO_SOMETHING'
    """
    parts = identifier.split("_")
    return Identifier("_".join(part.upper() for part in parts))


# fmt: off
@require(
    lambda identifier:
    identifier[0].isupper(),
    "Interface names must start with a capital letter"
)
# fmt: on
def interface_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a class based on its meta-model ``identifier``.

    >>> interface_name(Identifier("Something"))
    'ISomething'

    >>> interface_name(Identifier("URL_to_something"))
    'IUrlToSomething'

    >>> interface_name(Identifier("Something_to_URL"))
    'ISomethingToUrl'
    """
    return Identifier(f"I{aas_core_codegen.naming.capitalized_camel_case(identifier)}")


def property_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a public property based on its meta-model ``identifier``.

    Unlike a variable or a function, a property is declared as a ``PropertyName``,
    a grammar production which allows any identifier name, including the reserved
    words (*e.g.*, ``class Something { enum: string; }`` is valid TypeScript).
    Hence, we do *not* need to re-write the name even if it conflicts with
    a TypeScript keyword.

    >>> property_name(Identifier("something"))
    'something'

    >>> property_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> property_name(Identifier("URL_to_something"))
    'urlToSomething'
    """
    return aas_core_codegen.naming.lower_camel_case(identifier)


def function_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a function from its meta-model ``identifier``.

    A function is declared with a ``function`` statement, so its name is
    a binding identifier and can not be a reserved word. If the name conflicts
    with a TypeScript keyword such as ``enum``, it is translated as, *e.g.*,
    ``enuM``.

    >>> function_name(Identifier("do_something"))
    'doSomething'

    >>> function_name(Identifier("do_something_to_URL"))
    'doSomethingToUrl'

    >>> function_name(Identifier("enum"))
    'enuM'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def method_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an instance method based on its meta-model ``identifier``.

    Like a property (see :py:func:`property_name`), a method name is
    a ``PropertyName``, so it may be a reserved word without any conflict
    (*e.g.*, ``class Something { delete(): void {} }`` is valid TypeScript).
    Hence, we do *not* need to re-write the name even if it conflicts with
    a TypeScript keyword.

    >>> method_name(Identifier("do_something"))
    'doSomething'

    >>> method_name(Identifier("do_something_to_URL"))
    'doSomethingToUrl'
    """
    return aas_core_codegen.naming.lower_camel_case(identifier)


def argument_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for an argument based on its meta-model ``identifier``.

    A function or a method parameter is a binding identifier, so it can not be
    a reserved word (*e.g.*, ``function f(enum: string) {}`` is invalid
    TypeScript, and fails with "'enum' is not allowed as a parameter name.").
    If the name conflicts with a TypeScript keyword such as ``enum``, it is
    translated as, *e.g.*, ``enuM``.

    >>> argument_name(Identifier("something"))
    'something'

    >>> argument_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> argument_name(Identifier("enum"))
    'enuM'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def variable_name(identifier: Identifier) -> Identifier:
    """
    Generate a name for a variable based on its meta-model ``identifier``.

    A variable is declared with ``let``/``const``, so its name is a binding
    identifier and can not be a reserved word. If the name conflicts with
    a TypeScript keyword such as ``enum``, it is translated as, *e.g.*,
    ``enuM``.

    >>> variable_name(Identifier("something"))
    'something'

    >>> variable_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> variable_name(Identifier("enum"))
    'enuM'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)
