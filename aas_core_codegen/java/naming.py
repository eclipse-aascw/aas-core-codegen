"""Generate Java identifiers based on the identifiers from the meta-model."""
from typing import Union, Final, FrozenSet

from icontract import require

import aas_core_codegen.naming
from aas_core_codegen import intermediate
from aas_core_codegen.common import Identifier, assert_never

# NOTE (mristin):
# Unlike, *e.g.*, TypeScript, Java does *not* allow a reserved word to be used as
# *any* kind of identifier -- not a field, not a method, not a local variable, not
# a parameter (we verified this with ``javac`` 18.0.2-ea: *e.g.*,
# ``private String interface;`` and ``public String class() {}`` both fail with
# "<identifier> expected"). Hence every naming function which produces
# a lower-case-starting identifier (as opposed to a capitalized one, which can
# never collide with a keyword since all Java keywords are lower-case) has to
# guard against this.
#
# We downloaded this list from the Java Language Specification, SE 21, Section 3.9
# "Keywords" on 2026-08-28:
# https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.9
# (the keywords listed there, plus ``true``, ``false`` and ``null``, which are
# lexed as separate literal tokens by the JLS, but are, for our purposes, just as
# unusable as identifiers).
#
# We deliberately do *not* include the *contextual* keywords listed in the same
# section (*e.g.*, ``var``, ``yield``, ``record``, ``sealed``, ``permits``, ...),
# since those remain valid identifiers outside of their specific syntactic
# positions -- we verified with ``javac`` that, *e.g.*,
# ``public void m(String var, String yield, String record) {}`` compiles just
# fine.
_KEYWORD_SET: Final[FrozenSet[Identifier]] = frozenset(
    [
        Identifier("abstract"),
        Identifier("assert"),
        Identifier("boolean"),
        Identifier("break"),
        Identifier("byte"),
        Identifier("case"),
        Identifier("catch"),
        Identifier("char"),
        Identifier("class"),
        Identifier("const"),
        Identifier("continue"),
        Identifier("default"),
        Identifier("do"),
        Identifier("double"),
        Identifier("else"),
        Identifier("enum"),
        Identifier("extends"),
        Identifier("false"),
        Identifier("final"),
        Identifier("finally"),
        Identifier("float"),
        Identifier("for"),
        Identifier("goto"),
        Identifier("if"),
        Identifier("implements"),
        Identifier("import"),
        Identifier("instanceof"),
        Identifier("int"),
        Identifier("interface"),
        Identifier("long"),
        Identifier("native"),
        Identifier("new"),
        Identifier("null"),
        Identifier("package"),
        Identifier("private"),
        Identifier("protected"),
        Identifier("public"),
        Identifier("return"),
        Identifier("short"),
        Identifier("static"),
        Identifier("strictfp"),
        Identifier("super"),
        Identifier("switch"),
        Identifier("synchronized"),
        Identifier("this"),
        Identifier("throw"),
        Identifier("throws"),
        Identifier("true"),
        Identifier("try"),
        Identifier("void"),
        Identifier("volatile"),
        Identifier("while"),
    ]
)

assert all(len(keyword) > 1 for keyword in _KEYWORD_SET), (
    f"We expect all the keywords to be at least 2 characters, "
    f"but we got at least one which is not: {_KEYWORD_SET=}."
    f"We built the naming logic based on this assumption since we uppercase the "
    f"last letter whenever the identifier conflicts with a keyword."
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
    Transform the keyword identifier into a lowercase Java identifier.

    >>> _transform_keyword_to_lowercase_with_upper_last_letter(Identifier("class"))
    'clasS'
    """
    return Identifier(keyword[:-1] + keyword[-1].upper())


def interface_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java interface name based on its meta-model ``identifier``.

    >>> interface_name(Identifier("something"))
    'ISomething'

    >>> interface_name(Identifier("URL_to_something"))
    'IUrlToSomething'
    """
    return Identifier(f"I{aas_core_codegen.naming.capitalized_camel_case(identifier)}")


def enum_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for an enum based on its meta-model ``identifier``.

    >>> enum_name(Identifier("something"))
    'Something'

    >>> enum_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def enum_literal_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for an enum literal based on its meta-model ``identifier``.

    >>> enum_literal_name(Identifier("something"))
    'SOMETHING'

    >>> enum_literal_name(Identifier("URL_to_something"))
    'URL_TO_SOMETHING'
    """
    return aas_core_codegen.naming.upper_snake_case(identifier)


def class_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a class based on its meta-model ``identifier``.

    >>> class_name(Identifier("something"))
    'Something'

    >>> class_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def union_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a named union based on its meta-model ``identifier``.

    >>> union_name(Identifier("something"))
    'Something'

    >>> union_name(Identifier("URL_to_something"))
    'UrlToSomething'
    """
    return aas_core_codegen.naming.capitalized_camel_case(identifier)


def name_of(
    something: Union[
        intermediate.Enumeration,
        intermediate.ConcreteClass,
        intermediate.Interface,
        intermediate.NamedUnion,
    ]
) -> Identifier:
    """Dispatch to the appropriate naming function."""
    if isinstance(something, intermediate.Enumeration):
        return enum_name(something.name)

    elif isinstance(something, intermediate.ConcreteClass):
        return class_name(something.name)

    elif isinstance(something, intermediate.Interface):
        return interface_name(something.name)

    elif isinstance(something, intermediate.NamedUnion):
        return union_name(something.name)

    else:
        assert_never(something)

    raise AssertionError("Should not have gotten here")


def property_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a public property based on its meta-model ``identifier``.

    A field is a plain identifier in Java, so it can not be a reserved word
    (unlike, *e.g.*, in TypeScript). If the name conflicts with a Java keyword
    such as ``class``, it is translated as, *e.g.*, ``clasS``. This is ugly, but
    we couldn't find a better convention that hurts less.

    >>> property_name(Identifier("something"))
    'something'

    >>> property_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> property_name(Identifier("class"))
    'clasS'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def private_property_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a private property based on the ``identifier``.

    If the name conflicts with a Java keyword such as ``class``, it is
    translated as, *e.g.*, ``clasS``. This is ugly, but we couldn't find
    a better convention that hurts less.

    >>> private_property_name(Identifier("something"))
    'something'

    >>> private_property_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> private_property_name(Identifier("class"))
    'clasS'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def private_method_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a private method based on the ``identifier``.

    If the name conflicts with a Java keyword such as ``class``, it is
    translated as, *e.g.*, ``clasS``. This is ugly, but we couldn't find
    a better convention that hurts less.

    >>> private_method_name(Identifier("do_something"))
    'doSomething'

    >>> private_method_name(Identifier("do_something_to_URL"))
    'doSomethingToUrl'

    >>> private_method_name(Identifier("class"))
    'clasS'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def method_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a member method based on its meta-model ``identifier``.

    A method name is a plain identifier in Java, so it can not be a reserved
    word. If the name conflicts with a Java keyword such as ``class``, it is
    translated as, *e.g.*, ``clasS``. This is ugly, but we couldn't find
    a better convention that hurts less.

    >>> method_name(Identifier("do_something"))
    'doSomething'

    >>> method_name(Identifier("do_something_to_URL"))
    'doSomethingToUrl'

    >>> method_name(Identifier("class"))
    'clasS'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def argument_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for an argument based on its meta-model ``identifier``.

    A parameter is a plain identifier in Java, so it can not be a reserved
    word. If the name conflicts with a Java keyword such as ``class``, it is
    translated as, *e.g.*, ``clasS``. This is ugly, but we couldn't find
    a better convention that hurts less.

    >>> argument_name(Identifier("something"))
    'something'

    >>> argument_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> argument_name(Identifier("class"))
    'clasS'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def variable_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a variable based on its meta-model ``identifier``.

    A local variable is a plain identifier in Java, so it can not be
    a reserved word. If the name conflicts with a Java keyword such as
    ``class``, it is translated as, *e.g.*, ``clasS``. This is ugly, but we
    couldn't find a better convention that hurts less.

    >>> variable_name(Identifier("something"))
    'something'

    >>> variable_name(Identifier("something_to_URL"))
    'somethingToUrl'

    >>> variable_name(Identifier("class"))
    'clasS'
    """
    if identifier in _KEYWORD_SET:
        return _transform_keyword_to_lowercase_with_upper_last_letter(identifier)

    return aas_core_codegen.naming.lower_camel_case(identifier)


def getter_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a getter on its meta-model ``identifier``.

    >>> getter_name(Identifier("something"))
    'getSomething'

    >>> getter_name(Identifier("something_to_URL"))
    'getSomethingToUrl'
    """
    return Identifier(
        f"get{aas_core_codegen.naming.capitalized_camel_case(identifier)}"
    )


def setter_name(identifier: Identifier) -> Identifier:
    """
    Generate a Java name for a setter on its meta-model ``identifier``.

    >>> setter_name(Identifier("something"))
    'setSomething'

    >>> setter_name(Identifier("something_to_URL"))
    'setSomethingToUrl'
    """
    return Identifier(
        f"set{aas_core_codegen.naming.capitalized_camel_case(identifier)}"
    )
