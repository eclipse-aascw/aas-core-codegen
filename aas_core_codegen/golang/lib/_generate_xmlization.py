"""Generate code for XML de/serialization."""

import io
from typing import Tuple, Optional, List, Set, Union

from icontract import ensure, require

from aas_core_codegen import intermediate, naming, specific_implementations
from aas_core_codegen.common import (
    Error,
    Stripped,
    Identifier,
    assert_never,
    indent_but_first_line,
)
from aas_core_codegen.golang import (
    common as golang_common,
    naming as golang_naming,
    pointering as golang_pointering,
)
from aas_core_codegen.golang.common import (
    INDENT as I,
    INDENT2 as II,
    INDENT3 as III,
    INDENT4 as IIII,
    INDENT5 as IIIII,
    INDENT6 as IIIIII,
)

# region Shared between the de-serialization and the serialization


# NOTE (mristin):
# A Golang primitive is not usable as a part of an identifier as it is spelled
# (``[]byte``), so the primitives need monikers of their own. The monikers are
# *lower-case* on purpose: every one of our types is named through
# :py:func:`aas_core_codegen.naming.capitalized_camel_case`, which always yields
# an upper-case initial, so a primitive moniker can never be confused for one of
# our types -- not even for an enumeration which somebody named ``String``. They
# are keyed by the meta-model primitive rather than by the Golang spelling, so that
# the mapping is total by construction.
_PRIMITIVE_TYPE_TO_MONIKER = {
    intermediate.PrimitiveType.BOOL: "bool",
    intermediate.PrimitiveType.INT: "long",
    intermediate.PrimitiveType.FLOAT: "double",
    intermediate.PrimitiveType.STR: "string",
    intermediate.PrimitiveType.BYTEARRAY: "bytes",
}
assert all(
    literal in _PRIMITIVE_TYPE_TO_MONIKER for literal in intermediate.PrimitiveType
)
assert all(
    moniker.islower() for moniker in _PRIMITIVE_TYPE_TO_MONIKER.values()
), "The primitive monikers have to be lower-case, see the note above"


@ensure(lambda result: "_" not in result)
def _leaf_moniker(type_anno: intermediate.AtomicTypeAnnotation) -> str:
    """
    Name the type of ``type_anno`` as a part of an identifier.

    Everything which is not a primitive is named as the Golang type is, so that
    the name of a function can not drift apart from the type it operates on.

    The result must not contain an underscore, since the underscore is what
    separates a moniker from the rest of a composed name -- see the note above
    :py:func:`_scalar_item_reader_name`.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return _PRIMITIVE_TYPE_TO_MONIKER[primitive_type]

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Unexpected type annotation for a moniker: {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return golang_naming.enum_name(our_type.name)

    if isinstance(our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)):
        return golang_naming.interface_name(our_type.name)

    assert isinstance(
        our_type, intermediate.NamedUnion
    ), f"Unexpected our type for a moniker: {our_type}"

    return golang_naming.union_name(our_type.name)


class _ScalarItem:
    """
    Specify a scalar value wrapped in an element of a fixed name.

    A scalar element is not self-describing: its name denotes its *position*, ``v``
    in a list and ``v1``, ``v2``, *etc.* in a tuple, and never its type. Both sides
    therefore need a function per scalar type *and* element name: the reader checks
    the name (see :py:func:`_generate_read_scalar_item`), the writer writes it (see
    :py:func:`_generate_write_scalar_item`), so that neither a container nor its
    items need to know anything about the other.
    """

    def __init__(
        self,
        type_anno: intermediate.AtomicTypeAnnotation,
        element_name: str,
    ) -> None:
        """Initialize with the given values."""
        self.type_anno = type_anno
        self.element_name = element_name


# NOTE (mristin):
# Every name which spells out a *type* puts the moniker last, after an underscore:
# ``readAtV{i}_{M}``, ``readTextAs_{M}``, ``writeListOf_{M}``,
# ``writeTupleOf{N}_{M}_{M}...`` and their duals. A tuple states its arity and
# separates its items, so these names are a Polish notation over ``_``-separated
# tokens. Since a leaf moniker never contains an underscore (see
# :py:func:`_leaf_moniker`), the encoding is injective -- two different types can
# not be given the same moniker, and hence two different functions can not be
# given the same name.
#
# The underscore also keeps these names apart from the ones keyed by one of our
# symbols -- ``read*AsSequence``, ``read*Dispatched`` *etc.* Those go through
# :py:func:`aas_core_codegen.golang.naming.private_function_name`, which never
# emits an underscore.


@require(lambda element_name: element_name.startswith("v"))
def _scalar_item_reader_name(
    type_anno: intermediate.AtomicTypeAnnotation, element_name: str
) -> Identifier:
    """Name the function reading a scalar ``type_anno`` in ``element_name``."""
    return Identifier(f"readAtV{element_name[1:]}_{_leaf_moniker(type_anno)}")


@require(lambda element_name: element_name.startswith("v"))
def _scalar_item_writer_name(
    type_anno: intermediate.AtomicTypeAnnotation, element_name: str
) -> Identifier:
    """Name the function writing a scalar ``type_anno`` in ``element_name``."""
    return Identifier(f"writeAtV{element_name[1:]}_{_leaf_moniker(type_anno)}")


def _enum_text_reader_name(enumeration: intermediate.Enumeration) -> Identifier:
    """Name the function reading the text content of an element as ``enumeration``."""
    return Identifier(f"readTextAs_{golang_naming.enum_name(enumeration.name)}")


def _enum_text_writer_name(enumeration: intermediate.Enumeration) -> Identifier:
    """Name the function writing ``enumeration`` as the text content of an element."""
    return Identifier(f"writeAsText_{golang_naming.enum_name(enumeration.name)}")


def _list_content_writer_name(
    items_type_anno: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """Name the function which writes the content of a list of ``items_type_anno``."""
    return Stripped(f"writeListOf_{_leaf_moniker(items_type_anno)}")


def _tuple_content_writer_name(type_anno: intermediate.TupleTypeAnnotation) -> Stripped:
    """Name the function which writes the content of a tuple of ``type_anno``."""
    monikers = []  # type: List[str]
    for item_type_anno in type_anno.items:
        assert isinstance(item_type_anno, intermediate.AtomicTypeAnnotationAsTuple)
        monikers.append(_leaf_moniker(item_type_anno))

    joined = "_".join(monikers)

    return Stripped(f"writeTupleOf{len(monikers)}_{joined}")


def _requires_dispatch(type_anno: intermediate.TypeAnnotation) -> bool:
    """
    Check whether a *single* property of ``type_anno`` is de/serialized by dispatch.

    A single property of a concrete class without concrete descendants is wrapped in
    an element named after the *property*, not after the class, so there is no
    discriminator to dispatch on. Everything else polymorphic -- an abstract class,
    a concrete class with concrete descendants, and a named union -- is wrapped twice,
    the inner element naming the concrete alternative.
    """
    if not isinstance(type_anno, intermediate.OurTypeAnnotation):
        return False

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.ConcreteClass):
        return len(our_type.concrete_descendants) > 0

    return isinstance(our_type, (intermediate.AbstractClass, intermediate.NamedUnion))


class _Requirements:
    """Specify which of the optional de/serialization functions are needed."""

    def __init__(
        self,
        dispatched_type_ids: Set[int],
        scalar_items: List[_ScalarItem],
        list_items_type_annos: List[intermediate.AtomicTypeAnnotation],
        tuple_type_annos: List[intermediate.TupleTypeAnnotation],
    ) -> None:
        """Initialize with the given values."""
        #: IDs of our types for which a ``read*Dispatched`` function must be generated
        self.dispatched_type_ids = dispatched_type_ids

        #: Scalar items to be de/serialized, in the order of the first occurrence
        self.scalar_items = scalar_items

        #: Items of the lists to be serialized, in the order of the first occurrence
        self.list_items_type_annos = list_items_type_annos

        #: Tuples to be serialized, in the order of the first occurrence
        self.tuple_type_annos = tuple_type_annos


def _collect_requirements(
    symbol_table: intermediate.SymbolTable,
) -> _Requirements:
    """
    Collect the de/serialization functions which are actually reachable.

    ``Unmarshal`` dispatches to ``read*AsSequence`` and ``Marshal`` to
    ``write*AsSequence`` of *every* concrete class, so every concrete class is
    reachable, and it suffices to look at the properties of the concrete classes:
    a ``read*Dispatched``, a scalar item function and a tuple writer are called only
    from a property.
    """
    dispatched_type_ids = set()  # type: Set[int]

    scalar_items = []  # type: List[_ScalarItem]
    observed_scalar_items = set()  # type: Set[Tuple[str, str]]

    list_items_type_annos = []  # type: List[intermediate.AtomicTypeAnnotation]
    observed_list_writers = set()  # type: Set[str]

    tuple_type_annos = []  # type: List[intermediate.TupleTypeAnnotation]
    observed_tuple_writers = set()  # type: Set[str]

    def require_item(
        item_type_anno: intermediate.AtomicTypeAnnotation, element_name: str
    ) -> None:
        """Require the de/serialization of an item in ``element_name``."""
        if isinstance(item_type_anno, intermediate.OurTypeAnnotation) and isinstance(
            item_type_anno.our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ):
            dispatched_type_ids.add(id(item_type_anno.our_type))
            return

        key = (_leaf_moniker(item_type_anno), element_name)
        if key not in observed_scalar_items:
            observed_scalar_items.add(key)
            scalar_items.append(
                _ScalarItem(type_anno=item_type_anno, element_name=element_name)
            )

    for cls in symbol_table.concrete_classes:
        for prop in cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(type_anno, intermediate.ListTypeAnnotation):
                assert isinstance(
                    type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
                )
                require_item(type_anno.items, "v")

                writer_name = _list_content_writer_name(type_anno.items)
                if writer_name not in observed_list_writers:
                    observed_list_writers.add(writer_name)
                    list_items_type_annos.append(type_anno.items)

            elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
                for i, item_type_anno in enumerate(type_anno.items):
                    assert isinstance(
                        item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                    )
                    require_item(item_type_anno, f"v{i + 1}")

                writer_name = _tuple_content_writer_name(type_anno)
                if writer_name not in observed_tuple_writers:
                    observed_tuple_writers.add(writer_name)
                    tuple_type_annos.append(type_anno)

            elif _requires_dispatch(type_anno):
                assert isinstance(type_anno, intermediate.OurTypeAnnotation)
                dispatched_type_ids.add(id(type_anno.our_type))

    return _Requirements(
        dispatched_type_ids=dispatched_type_ids,
        scalar_items=scalar_items,
        list_items_type_annos=list_items_type_annos,
        tuple_type_annos=tuple_type_annos,
    )


# endregion


# region De-serialization


def _generate_deserialization_error_and_its_methods() -> List[Stripped]:
    """Generate code to represent the deserialization error."""
    return [
        Stripped(
            f"""\
// Represent an error during the de-serialization.
//
// Implements `error`.
type DeserializationError struct{{
{I}Path *aasreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newDeserializationError(message string) *DeserializationError {{
{I}return &DeserializationError{{
{II}Path: &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func (de *DeserializationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}de.PathString(),
{II}de.Message,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Render the path as a string.
func (de *DeserializationError) PathString() string {{
{I}return aasreporting.ToRelativeXPath(de.Path)
}}"""
        ),
    ]


def _generate_is_whitespace() -> Stripped:
    return Stripped(
        f"""\
// Check if the string `s` consists only of whitespace.
//
// An empty string causes panic — please cover that case before.
func isWhitespace(s string) bool {{
{I}if len(s) == 0 {{
{II}panic("Unexpected empty string")
{I}}}
{I}for _, c := range s {{
{II}if !unicode.IsSpace(c) {{
{III}return false
{II}}}
{I}}}
{I}return true
}}"""
    )


def _generate_read_next() -> Stripped:
    return Stripped(
        f"""\
// Read the next token from the `decoder` given the `current` token.
//
// If `current` token is [eof], return [eof].
func readNext(decoder *xml.Decoder, current xml.Token) (next xml.Token, err error) {{
{I}if _, isEOF := current.(eof); isEOF {{
{II}next = current
{II}return
{I}}}

{I}var tokenErr error
{I}next, tokenErr = decoder.Token()
{I}if tokenErr != nil {{
{II}if tokenErr == io.EOF {{
{III}next = &eof{{}}
{III}return
{II}}}

{II}err = tokenErr
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_skip_empty_text_whitespace_and_comments() -> Stripped:
    return Stripped(
        f"""\
// Read all the possible whitespace and comments.
//
// Return the `next` token which is neither empty text, nor whitespace nor comment,
// or [eof], if we reached the end-of-file.
//
// If we already reached the end-of-file, simply return [eof].
func skipEmptyTextWhitespaceAndComments(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (next xml.Token, err error) {{
{I}stop := false
{I}for !stop {{
{II}if _, isEOF := current.(eof); isEOF {{
{III}break
{II}}}

{II}switch et := current.(type) {{
{II}case xml.CharData:
{III}text := string(et)
{III}if len(text) != 0 && !isWhitespace(text) {{
{IIII}stop = true
{III}}} else {{
{IIII}// We should proceed to the next token.
{III}}}
{II}case xml.Comment:
{III}// We should proceed to the next token.
{II}default:
{III}stop = true
{II}}}

{II}if !stop {{
{III}current, err = readNext(decoder, current)
{III}if err != nil {{
{IIII}return
{III}}}
{II}}}
{I}}}

{I}next = current
{I}return
}}"""
    )


def _generate_read_text() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data).
//
// Any comment tokens are skipped.
//
// Match a run of the four characters which XML calls whitespace.
var whitespaceRunRe = regexp.MustCompile("[ \\t\\n\\r]+")

// Normalize `text` the way `whiteSpace="collapse"` prescribes.
//
// Every atomic XSD type except a string, and every type derived from one by
// restriction, fixes `whiteSpace` to `collapse`, and a schema author can not
// change it. A tab, a line feed and a carriage return each become a space,
// a run of spaces becomes one space, and the leading and trailing spaces go.
// Only the result of that is a lexical representation to be matched.
//
// Mind that this strips only the whitespace *around* the value: a space
// within it survives as a single space, so "2  3" becomes "2 3", which is
// still no number.
//
// See: https://www.w3.org/TR/xmlschema-2/#rf-whiteSpace
func collapseWhitespace(text string) string {{
{I}return strings.Trim(whitespaceRunRe.ReplaceAllString(text, " "), " ")
}}

// Drop every whitespace character of `text`.
//
// This is what `xs:base64Binary` needs: it allows whitespace between
// the characters and not only around them, so collapsing is not enough --
// the decoder accepts none of it.
func removeWhitespace(text string) string {{
{I}return whitespaceRunRe.ReplaceAllString(text, "")
}}

// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readText(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (text string, next xml.Token, err error) {{
{I}b := &strings.Builder{{}}

{I}stop := false
{I}for {{
{II}if _, isEOF := current.(eof); isEOF {{
{III}err = newDeserializationError(
{IIII}"Expected to read text, but reached the end-of-file",
{III})
{III}return
{II}}}

{II}switch et := current.(type) {{
{II}case xml.CharData:
{III}b.WriteString(string(et))
{III}// Proceed to the next token.
{II}case xml.Comment:
{III}// Proceed to the next token.
{II}default:
{III}stop = true
{II}}}

{II}if !stop {{
{III}current, err = readNext(decoder, current)
{III}if err != nil {{
{IIII}return
{III}}}
{II}}} else {{
{III}break
{II}}}
{I}}}

{I}next = current
{I}text = b.String()
{I}return
}}"""
    )


def _generate_read_text_as_bool() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:boolean`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAs_bool(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value bool, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}text = collapseWhitespace(text)

{I}switch text {{
{I}case "1":
{II}value = true
{I}case "true":
{II}value = true
{I}case "0":
{II}value = false
{I}case "false":
{II}value = false
{I}default:
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:boolean, but got: %s",
{IIII}text,
{III}),
{II})
{I}}}
{I}if err != nil {{
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_read_text_as_long() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:long`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAs_long(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value int64, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}text = collapseWhitespace(text)

{I}var parseErr error
{I}value, parseErr = strconv.ParseInt(text, 10, 64)
{I}if parseErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:long, but it could not be parsed: %s: %s",
{IIII}parseErr.Error(), text,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_is_valid_xs_double() -> List[Stripped]:
    """
    Generate regular expression to check ``xs:double`` values.

    While there might be a function in the meta-model itself with the same name in
    the verification, we provide a separate function here so that it works for all
    meta-models.
    """
    return [
        Stripped(
            f"""\
func constructXsDoubleRe() *regexp.Regexp {{
{I}doubleRep := "((\\\\+|-)?([0-9]+(\\\\.[0-9]*)?|\\\\.[0-9]+)([Ee](\\\\+|-)?[0-9]+)?|-?INF|NaN)"
{I}pattern := aascommon.Concat(
{II}"^",
{II}doubleRep,
{II}"$",
{I})

{I}return regexp.MustCompile(
{II}pattern,
{I})
}}"""
        ),
        Stripped(
            """\
var xsDoubleRe = constructXsDoubleRe()"""
        ),
        Stripped(
            f"""\
// Check that text conforms to the pattern of an `xs:double`.
//
// See: https://www.w3.org/TR/xmlschema-2/#double
//
//   - `text`: Text to be checked
//   - Return True if the text conforms to the pattern
func isValidXsDouble(text string) bool {{
{I}return xsDoubleRe.MatchString(
{II}text,
{I})
}}"""
        ),
    ]


def _generate_read_text_as_double() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a representation of a `xs:double`.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAs_double(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value float64, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}text = collapseWhitespace(text)

{I}// We need to check explicitly for the regular expression since
{I}// strconv.ParseFloat is too permissive. For example, it accepts "nan"
{I}// although only "NaN" is valid.
{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}if !isValidXsDouble(text) {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:double, but got: %s",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}var parseErr error
{I}value, parseErr = strconv.ParseFloat(text, 64)
{I}if parseErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected a value as xs:double, but it could not be parsed: %s: %s",
{IIII}parseErr.Error(), text,
{III}),
{II})
{II}return
{I}}}

{I}// NOTE:
{I}// We explicitly do not check for loss of precision, as the majority of people will
{I}// use string representation of the floating point numbers ignoring the precision
{I}// issues. For example, the closest double-precision number to the number `359.9` is
{I}// `359.8999999999999772626324556767940521240234375`, but most people will simply
{I}// give `359.9` as the value.

{I}return
}}"""
    )


def _generate_read_text_as_bytes() -> Stripped:
    return Stripped(
        f"""\
// Consume the text tokens (char data) as a base64-encoded bytes.
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func readTextAs_bytes(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value []byte, next xml.Token, err error) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}
{I}// NOTE:
{I}// xs:base64Binary allows whitespace between the characters, and not only
{I}// around them, while the decoder accepts none of it. So every whitespace
{I}// character is dropped, and not merely collapsed.
{I}//
{I}// See: https://www.w3.org/TR/xmlschema-2/#base64Binary
{I}text = removeWhitespace(text)

{I}var decodingErr error
{I}value, decodingErr = b64.StdEncoding.DecodeString(text)
{I}if decodingErr != nil {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Text could not be decoded as base64: %s",
{IIII}decodingErr.Error(),
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_check_start_element() -> Stripped:
    return Stripped(
        f"""\
// Check that the `current` token is a valid start element, *i.e.*, lives in [Namespace]
// and contains no attributes.
func checkStartElement(
{I}current xml.StartElement,
) (err error) {{
{I}unexpectedAttr := 0
{I}for _, attr := range current.Attr {{
{II}if (attr.Name.Space == "" && attr.Name.Local == "xmlns") ||
{III}attr.Name.Space == "xmlns" {{
{III}continue
{II}}}

{II}unexpectedAttr++
{I}}}
{I}if unexpectedAttr != 0 {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected no attributes except 'xmlns' in the start element, "+
{IIIII}"but got %d in the start element %s",
{IIII}unexpectedAttr, current.Name.Local,
{III}),
{II})
{II}return
{I}}}

{I}if current.Name.Space != Namespace {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected only start elements in the namespace %s, "+
{IIIII}"but got a start element %s in the namespace %s",
{IIII}Namespace, current.Name.Local, current.Name.Space,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_extract_local_name_from_start_element() -> Stripped:
    return Stripped(
        f"""\
// Expect a valid start element (as defined in [checkStartElement]) and extract its
// `local` name.
//
// This function is meant to be called whenever you know the runtime type of a token.
// If you do not know the runtime type, call [parseAsStartElementAndExtractLocalName]
// so that you can succinctly check the runtime type as well.
func extractLocalNameFromStartElement(
{I}current xml.StartElement,
) (local string, err error) {{
{I}err = checkStartElement(current)
{I}if err != nil {{
{II}return
{I}}}

{I}local = current.Name.Local
{I}return
}}"""
    )


def _generate_parse_as_start_element_and_extract_local_name() -> Stripped:
    return Stripped(
        f"""\
// Expect a valid start element (as defined in [checkStartElement]) and extract its
// local name.
//
// Valid means that we check that the start element lives in [Namespace] and contains
// no attributes.
//
// If you know the runtime type of `current` token, call
// [parseLocalNameFromStartElement] instead to save a cast.
func parseAsStartElementAndExtractLocalName(
{I}current xml.Token,
) (local string, err error) {{
{I}if _, isEOF := current.(eof); isEOF {{
{II}err = newDeserializationError(
{III}"Expected a start element, but reached the end-of-file",
{II})
{II}return
{I}}}

{I}et, ok := current.(xml.StartElement)
{I}if !ok {{
{II}switch v := current.(type) {{
{II}case xml.EndElement:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got an end element %s in namespace %s",
{IIIII}v.Name.Local, v.Name.Space,
{IIII}),
{III})
{II}case xml.CharData:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got text %s",
{IIIII}string(v),
{IIII}),
{III})
{II}default:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a start element, but got %T: %v",
{IIIII}current, current,
{IIII}),
{III})
{II}}}
{II}return
{I}}}

{I}local, err = extractLocalNameFromStartElement(et)
{I}return
}}"""
    )


def _generate_check_end_element() -> Stripped:
    return Stripped(
        f"""\
// Check that the `current` token is an end element, living in [Namespace], and
// having the `local` name.
func checkEndElement(current xml.Token, local string) (err error) {{
{I}if _, isEOF := current.(eof); isEOF {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s, but reached the end-of-file",
{IIII}local,
{III}),
{II})
{II}return
{I}}}

{I}et, ok := current.(xml.EndElement)
{I}if !ok {{
{II}switch v := current.(type) {{
{II}case xml.StartElement:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got a start element %s in namespace %s",
{IIIII}local, v.Name.Local, v.Name.Space,
{IIII}),
{III})
{II}case xml.CharData:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got text %s",
{IIIII}local, string(v),
{IIII}),
{III})
{II}default:
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected an end element %s, but got %T: %v",
{IIIII}local, current, current,
{IIII}),
{III})
{II}}}
{II}return
{I}}}

{I}if et.Name.Space != Namespace {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s in the namespace %s, "+
{IIIII}"but got an end element in the namespace %s",
{IIII}local, Namespace, et.Name.Space,
{III}),
{II})
{II}return
{I}}}

{I}if et.Name.Local != local {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Expected an end element %s, but got an end element %s",
{IIII}local, et.Name.Local,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


def _generate_error_constructors() -> List[Stripped]:
    """Generate the constructors of the recurring de-serialization errors."""
    return [
        Stripped(
            f"""\
// Report that the required property with the given `name` has not been observed.
func missingProperty(name string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"The required property '%s' is missing",
{III}name,
{II}),
{I})
}}"""
        ),
        Stripped(
            f"""\
// Report that we got a start element with the `local` name, but expected a start
// element with the `expectedLocal` name.
func unexpectedStartElement(local string, expectedLocal string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected a start element with local name %s, "+
{IIII}"but got a start element with local name %s",
{III}expectedLocal, local,
{II}),
{I})
}}"""
        ),
        Stripped(
            f"""\
// Report that the start element with the `local` name does not discriminate any of
// the alternatives of `expectedType`.
func unexpectedDiscriminator(local string, expectedType string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected start element %s as discriminator for %s",
{III}local, expectedType,
{II}),
{I})
}}"""
        ),
        Stripped(
            f"""\
// Report that we got an item delimited by a start element with the `local` name,
// but expected the delimiter with the `expectedLocal` name.
func unexpectedItemElement(local string, expectedLocal string) error {{
{I}return newDeserializationError(
{II}fmt.Sprintf(
{III}"Expected start element %s as an item delimiter, "+
{IIII}"but got %s",
{III}expectedLocal, local,
{II}),
{I})
}}"""
        ),
    ]


def _generate_read_element_dispatched() -> Stripped:
    """Generate the function to read a single value wrapped in an XML element."""
    return Stripped(
        f"""\
// Read a value wrapped in a single XML element, dispatching on the local name of
// that element.
//
// The element is read in full: the resulting `next` token points to the first token
// just after the end element.
//
// This is the *only* place which frames an XML element around a value. Both
// [readListOf] and the `readTuple*` functions delegate the framing here, so that
// a scalar item and an instance item differ only in the given `readByLocal`, and
// never in the container which reads them.
//
// `T` is left unconstrained (instead of `aastypes.IClass`) since this
// function never invokes any `aastypes.IClass` method on `T` -- this lets it
// be reused for a scalar and for a named union as well, the latter being
// deliberately not an `aastypes.IClass` itself.
func readElementDispatched[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}readByLocal func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (value T, next xml.Token, err error) {{
{I}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var local string
{I}local, err = parseAsStartElementAndExtractLocalName(current)
{I}if err != nil {{
{II}return
{I}}}

{I}// Move the current to the content of the XML element
{I}current, err = readNext(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}value, current, err = readByLocal(decoder, current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}err = checkEndElement(current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}next, err = readNext(decoder, current)
{I}return
}}"""
    )


def _generate_read_list_of() -> Stripped:
    """Generate the function to read a list of values as a sequence of XML elements."""
    return Stripped(
        f"""\
// Read a list of values as a sequence of XML elements.
//
// Every start element is considered to mark the start of an item serialization. We
// stop the reading as soon as we encounter a non-start element.
//
// That last non-start element is returned as `next` element.
//
// An item is read with [readElementDispatched], so `readItem` decides on its own
// which local names it accepts. A list of instances and a list of scalars therefore
// share this one function: an instance is discriminated by its own element name,
// while a scalar is expected in an element named `v`.
//
// `T` is left unconstrained (instead of `aastypes.IClass`) since this
// function never invokes any `aastypes.IClass` method on `T` -- this lets it
// be reused for a list of scalars and for a list of a named union as well,
// the latter being deliberately not an `aastypes.IClass` itself.
func readListOf[T any](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}readItem func(
{II}aDecoder *xml.Decoder,
{II}aCurrent xml.Token,
{II}aLocal string,
{I}) (value T, aNext xml.Token, anErr error),
) (values []T, next xml.Token, err error) {{
{I}i := 0
{I}for {{
{II}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{II}if err != nil {{
{III}return
{II}}}

{II}if _, ok := current.(xml.StartElement); !ok {{
{III}break
{II}}}

{II}var value T
{II}var valueErr error
{II}value, current, valueErr = readElementDispatched(
{III}decoder, current, readItem,
{II})
{II}if valueErr != nil {{
{III}if deseriaErr, ok := valueErr.(*DeserializationError); ok {{
{IIII}deseriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{Index: i}},
{IIII})
{III}}}
{III}err = valueErr
{III}return
{II}}}

{II}values = append(values, value)

{II}i++
{I}}}

{I}next = current
{I}return
}}"""
    )


def _generate_read_optional() -> Stripped:
    """Generate the function to turn a just-read value into a pointer."""
    return Stripped(
        f"""\
// Turn a just-read value into a pointer, so that it can be stored in an optional
// property.
//
// An optional is represented as a pointer, so the value has to live outside the
// caller's frame. This allocates exactly the one value that the caller would
// otherwise allocate by taking the address of its own local variable, and no more.
//
// The arguments are the *results* of a read, not the reader itself. Go passes
// a multi-valued call on as a complete argument list, so this composes with any read,
// no matter how many arguments that read takes on its own --
// `readOptional(readTextAs_long(decoder, current))` just as much as
// `readOptional(readTuple2(decoder, current, readAtV1_X, readAtV2_Y))`, which no
// reader-taking signature could express, since the item readers of a tuple vary in
// number and in type.
func readOptional[T any](
{I}value T,
{I}current xml.Token,
{I}err error,
) (*T, xml.Token, error) {{
{I}if err != nil {{
{II}return nil, current, err
{I}}}

{I}return &value, current, nil
}}"""
    )


def _generate_next_property() -> Stripped:
    """Generate the function to advance to the next property of an instance."""
    return Stripped(
        f"""\
// Advance to the next property of an instance serialized as a sequence of XML
// elements, and return the `local` name of the corresponding start element.
//
// The resulting `next` token points to the content of that element.
//
// If there are no more properties, `ok` is false and `next` points to the token
// which stopped the reading, be it a non-start element or [eof].
//
// `interfaceName` is only used for error reporting.
func nextProperty(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}interfaceName string,
) (local string, next xml.Token, ok bool, err error) {{
{I}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}if _, isEOF := current.(eof); isEOF {{
{II}next = current
{II}return
{I}}}

{I}startElement, isStartElement := current.(xml.StartElement)
{I}if !isStartElement {{
{II}if charData, isCharData := current.(xml.CharData); isCharData {{
{III}err = newDeserializationError(
{IIII}fmt.Sprintf(
{IIIII}"Expected a sequence of XML elements representing properties "+
{IIIIII}"of %s, but got text: %s",
{IIIII}interfaceName, string(charData),
{IIII}),
{III})
{III}return
{II}}}

{II}next = current
{II}return
{I}}}

{I}local, err = extractLocalNameFromStartElement(startElement)
{I}if err != nil {{
{II}return
{I}}}

{I}// Move the current to the content of the XML element
{I}next, err = readNext(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}ok = true
{I}return
}}"""
    )


def _generate_conclude_property() -> Stripped:
    """Generate the function to conclude the reading of a single property."""
    return Stripped(
        f"""\
// Conclude the reading of the property delimited by the element with the `local`
// name.
//
// If `valueErr` is set, report it in the context of that property. Otherwise,
// consume the end element, so that the resulting `next` token points to the first
// token just after it.
func concludeProperty(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
{I}valueErr error,
) (next xml.Token, err error) {{
{I}if valueErr != nil {{
{II}if deseriaErr, ok := valueErr.(*DeserializationError); ok {{
{III}deseriaErr.Path.PrependName(
{IIII}&aasreporting.NameSegment{{Name: local}},
{III})
{II}}}
{II}err = valueErr
{II}return
{I}}}

{I}current, err = skipEmptyTextWhitespaceAndComments(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}err = checkEndElement(current, local)
{I}if err != nil {{
{II}return
{I}}}

{I}next, err = readNext(decoder, current)
{I}return
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_read_tuple_helper(arity: int) -> Stripped:
    """Generate a generic function to read a tuple of the given ``arity``."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    type_params_joined = ", ".join(f"{t} any" for t in type_params)

    tuple_type = f"aascommon.Tuple{arity}[{', '.join(type_params)}]"

    params_joined = ",\n".join(
        f"readItem{i + 1} func(\n"
        f"{I}aDecoder *xml.Decoder,\n"
        f"{I}aCurrent xml.Token,\n"
        f"{I}aLocal string,\n"
        f") ({type_params[i]}, xml.Token, error)"
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
var item{i + 1} {type_params[i]}
item{i + 1}, current, err = readElementDispatched(
{I}decoder, current, readItem{i + 1},
)
if err != nil {{
{I}if deseriaErr, ok := err.(*DeserializationError); ok {{
{II}deseriaErr.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{Index: {i}}},
{II})
{I}}}
{I}return
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    item_fields_joined = "\n".join(f"Item{i + 1}: item{i + 1}," for i in range(arity))

    function_name = f"readTuple{arity}"

    return Stripped(
        f"""\
// Read a tuple of {arity} item(s) with `readItem1`, `readItem2`, *etc.* on
// the correspondingly positioned item, or return an error.
//
// Each item is framed by [readElementDispatched], so an item reader accepts or
// rejects the positional element name (`v1`, `v2`, *etc.*) on its own for a scalar
// item, and discriminates on the class element name for an instance item.
func {function_name}[{type_params_joined}](
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}{indent_but_first_line(params_joined, I)},
) (result {tuple_type}, next xml.Token, err error) {{
{I}{indent_but_first_line(item_blocks_joined, I)}

{I}result = {tuple_type}{{
{II}{indent_but_first_line(item_fields_joined, II)}
{I}}}
{I}next = current
{I}return
}}"""
    )


def _generate_read_text_as_enumeration(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    enum_name = golang_naming.enum_name(enumeration.name)
    from_string_name = golang_naming.function_name(
        Identifier(f"{enumeration.name}_from_string")
    )

    function_name = _enum_text_reader_name(enumeration)

    return Stripped(
        f"""\
// Consume the text tokens (char data) as a string-encoded literal of
// [aastypes.{enum_name}].
//
// Any comment tokens are skipped.
//
// The resulting `next` token points to the first token which is neither text
// nor comment.
//
// If we reached the end-of-file, `next` is an [eof] sentinel token.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (value aastypes.{enum_name},
{I}next xml.Token,
{I}err error,
) {{
{I}var text string
{I}text, next, err = readText(decoder, current)
{I}if err != nil {{
{II}return
{I}}}

{I}var ok bool
{I}value, ok = aasstringification.{from_string_name}(text)
{I}if !ok {{
{II}err = newDeserializationError(
{III}fmt.Sprintf(
{IIII}"Unexpected literal of {enum_name}: %v",
{IIII}text,
{III}),
{II})
{II}return
{I}}}

{I}return
}}"""
    )


_READ_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "readTextAs_bool",
    intermediate.PrimitiveType.INT: "readTextAs_long",
    intermediate.PrimitiveType.FLOAT: "readTextAs_double",
    intermediate.PrimitiveType.STR: "readText",
    intermediate.PrimitiveType.BYTEARRAY: "readTextAs_bytes",
}
assert all(
    literal in _READ_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _read_text_function(type_anno: intermediate.AtomicTypeAnnotation) -> Stripped:
    """Determine the function which reads the text of a scalar ``type_anno``."""
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Stripped(_READ_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])

    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    ), (
        f"Expected a scalar type annotation, but got {type_anno}; "
        f"the instances are read by dispatch on their own element name instead"
    )

    return Stripped(_enum_text_reader_name(type_anno.our_type))


def _item_reader_name(
    type_anno: intermediate.AtomicTypeAnnotation, element_name: str
) -> Stripped:
    """
    Determine the reader of an item of ``type_anno`` wrapped in ``element_name``.

    An instance is read by dispatch on its own element name, so ``element_name`` is
    disregarded in that case.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type,
        (
            intermediate.AbstractClass,
            intermediate.ConcreteClass,
            intermediate.NamedUnion,
        ),
    ):
        return Stripped(
            golang_naming.private_function_name(
                Identifier(f"read_{type_anno.our_type.name}_dispatched")
            )
        )

    return Stripped(_scalar_item_reader_name(type_anno, element_name))


def _generate_read_scalar_item(scalar_item: _ScalarItem) -> Stripped:
    """Generate the function to read a scalar item at a fixed element name."""
    function_name = _scalar_item_reader_name(
        scalar_item.type_anno, scalar_item.element_name
    )

    value_type = golang_common.generate_type(
        type_annotation=scalar_item.type_anno, types_package=Identifier("aastypes")
    )

    element_name_literal = golang_common.string_literal(scalar_item.element_name)

    return Stripped(
        f"""\
// Read a scalar item expected in the element `{scalar_item.element_name}`.
//
// The `current` token is expected to point to the content of that element, and
// the resulting `next` token points to its end element.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (value {value_type},
{I}next xml.Token,
{I}err error,
) {{
{I}if local != {element_name_literal} {{
{II}err = unexpectedItemElement(local, {element_name_literal})
{II}return
{I}}}

{I}return {_read_text_function(scalar_item.type_anno)}(decoder, current)
}}"""
    )


def _generate_snippet_to_switch_on_property_deserialization(
    cls: intermediate.ConcreteClass,
) -> Stripped:
    """
    Generate the switch block to dispatch how to read a property.

    The start element is expected to have been read. The variable ``local`` denotes
    the local name of the start element.

    The decoder points to the first token of the property content.

    The variables ``the*`` and ``found*`` will be set as well as ``valueErr``.
    """
    case_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        type_anno = intermediate.beneath_optional(prop.type_annotation)

        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        xml_prop_literal = golang_common.string_literal(prop.xml_name)

        case_body = None  # type: Optional[Stripped]

        if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation) or (
            isinstance(type_anno, intermediate.OurTypeAnnotation)
            and isinstance(
                type_anno.our_type,
                (intermediate.ConstrainedPrimitive, intermediate.Enumeration),
            )
        ):
            read_text_function = _read_text_function(type_anno)

            if golang_pointering.is_pointer_type(prop.type_annotation):
                case_body = Stripped(
                    f"""\
{prop_var}, current, valueErr = readOptional(
{I}{read_text_function}(decoder, current),
)"""
                )
            else:
                case_body = Stripped(
                    f"""\
{prop_var}, current, valueErr = {read_text_function}(
{I}decoder, current,
)"""
                )

        elif isinstance(type_anno, intermediate.OurTypeAnnotation):
            our_type = type_anno.our_type

            if isinstance(
                our_type, (intermediate.Enumeration, intermediate.ConstrainedPrimitive)
            ):
                raise AssertionError("Must have been handled before")

            elif isinstance(
                our_type,
                (
                    intermediate.AbstractClass,
                    intermediate.ConcreteClass,
                    intermediate.NamedUnion,
                ),
            ):
                if _requires_dispatch(type_anno):
                    read_dispatched = golang_naming.private_function_name(
                        Identifier(f"read_{our_type.name}_dispatched")
                    )

                    case_body = Stripped(
                        f"""\
{prop_var}, current, valueErr = readElementDispatched(
{I}decoder, current, {read_dispatched},
)"""
                    )
                else:
                    # NOTE (mristin):
                    # The property is wrapped in an element named after the property
                    # itself, and there is only a single alternative, so there is no
                    # discriminating element in-between to dispatch on.
                    read_as_sequence = golang_naming.private_function_name(
                        Identifier(f"read_{our_type.name}_as_sequence")
                    )

                    case_body = Stripped(
                        f"""\
{prop_var}, current, valueErr = {read_as_sequence}(
{I}decoder, current,
)"""
                    )

            else:
                assert_never(our_type)

        elif isinstance(type_anno, intermediate.ListTypeAnnotation):
            assert isinstance(
                type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
            ), (
                f"NOTE (mristin): We expect only lists of atomic values "
                f"at the moment, but you specified {type_anno}. "
                f"Please contact the developers if you need this feature."
            )

            read_item = _item_reader_name(type_anno.items, "v")

            case_body = Stripped(
                f"""\
{prop_var}, current, valueErr = readListOf(
{I}decoder, current, {read_item},
)"""
            )

        elif isinstance(type_anno, intermediate.TupleTypeAnnotation):
            arity = len(type_anno.items)

            item_readers = []  # type: List[Stripped]
            for i, item_type_anno in enumerate(type_anno.items):
                assert isinstance(
                    item_type_anno, intermediate.AtomicTypeAnnotationAsTuple
                ), (
                    f"NOTE (mristin): We expect only tuples of atomic values "
                    f"at the moment, but you specified {type_anno}. "
                    f"Please contact the developers if you need this feature."
                )

                item_readers.append(_item_reader_name(item_type_anno, f"v{i + 1}"))

            item_readers_joined = "\n".join(
                f"{item_reader}," for item_reader in item_readers
            )

            read_tuple = Stripped(
                f"""\
readTuple{arity}(
{I}decoder, current,
{I}{indent_but_first_line(item_readers_joined, I)}
)"""
            )

            if golang_pointering.is_pointer_type(prop.type_annotation):
                # NOTE (mristin):
                # A tuple is represented as a Go struct, which is not nilable, so
                # an optional tuple is a pointer, just like an optional scalar, and
                # goes through the very same ``readOptional``.
                case_body = Stripped(
                    f"""\
{prop_var}, current, valueErr = readOptional(
{I}{indent_but_first_line(read_tuple, I)},
)"""
                )
            else:
                case_body = Stripped(f"{prop_var}, current, valueErr = {read_tuple}")

        else:
            # noinspection PyTypeChecker
            assert_never(type_anno)

        assert case_body is not None

        if not isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))
            case_body = Stripped(f"{case_body}\n{found_var} = true")

        case_blocks.append(
            Stripped(
                f"""\
case {xml_prop_literal}:
{I}{indent_but_first_line(case_body, I)}"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}valueErr = newDeserializationError(
{II}"Unexpected property",
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
var valueErr error
switch local {{
{case_blocks_joined}
}}"""
    )


def _generate_read_as_sequence(cls: intermediate.ConcreteClass) -> Stripped:
    interface_name = golang_naming.interface_name(cls.name)
    interface_name_literal = golang_common.string_literal(interface_name)

    # region Initialize

    initialization_blocks = []  # type: List[Stripped]

    prop_var_initializations = []  # type: List[Stripped]
    for prop in cls.properties:
        prop_var = golang_naming.variable_name(Identifier(f"the_{prop.name}"))

        prop_var_type = golang_common.generate_type(
            type_annotation=prop.type_annotation, types_package=Identifier("aastypes")
        )

        prop_var_initializations.append(Stripped(f"var {prop_var} {prop_var_type}"))

    if len(prop_var_initializations) > 0:
        initialization_blocks.append(Stripped("\n".join(prop_var_initializations)))

    found_var_initializations = []  # type: List[Stripped]
    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

        found_var_initializations.append(Stripped(f"{found_var} := false"))

    if len(found_var_initializations) > 0:
        initialization_blocks.append(Stripped("\n".join(found_var_initializations)))

    if len(initialization_blocks) == 0:
        initialization_blocks.append(
            Stripped(
                f"""\
// No initialization as there are no properties
// in {interface_name}."""
            )
        )

    initialization = "\n\n".join(initialization_blocks)

    # endregion

    switch_snippet = _generate_snippet_to_switch_on_property_deserialization(cls=cls)

    # region Construct

    construct_blocks = []  # type: List[Stripped]

    for prop in cls.properties:
        if isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        found_var = golang_naming.variable_name(Identifier(f"found_{prop.name}"))

        xml_prop_literal = golang_common.string_literal(prop.xml_name)

        construct_blocks.append(
            Stripped(
                f"""\
if !{found_var} {{
{I}err = missingProperty({xml_prop_literal})
{I}return
}}"""
            )
        )

    constructing_statements = []  # type: List[Stripped]

    constructor_arguments = [
        golang_naming.variable_name(Identifier(f"the_{arg.name}"))
        for arg in cls.constructor.arguments
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation)
    ]  # type: List[Stripped]

    new_function = golang_naming.function_name(Identifier(f"new_{cls.name}"))

    if len(constructor_arguments) > 0:
        constructor_arguments_joined = "\n".join(
            f"{arg}," for arg in constructor_arguments
        )

        constructing_statements.append(
            Stripped(
                f"""\
instance = aastypes.{new_function}(
{I}{indent_but_first_line(constructor_arguments_joined, I)}
)"""
            )
        )
    else:
        constructing_statements.append(
            Stripped(f"instance = aastypes.{new_function}()")
        )

    for arg in cls.constructor.arguments:
        if not isinstance(arg.type_annotation, intermediate.OptionalTypeAnnotation):
            continue

        setter_name = golang_naming.setter_name(arg.name)
        prop_var = golang_naming.variable_name(Identifier(f"the_{arg.name}"))

        constructing_statements.append(Stripped(f"instance.{setter_name}({prop_var})"))

    construct_blocks.append(Stripped("\n".join(constructing_statements)))

    construct = "\n\n".join(construct_blocks)

    # endregion

    function_name = golang_naming.private_function_name(
        Identifier(f"read_{cls.name}_as_sequence")
    )

    return Stripped(
        f"""\
// De-serialize the instance of [aastypes.{interface_name}]
// as a sequence of XML elements, each representing a property
// of [aastypes.{interface_name}].
//
// The reading stops as soon as we encounter a non-start element, and we return
// that token as the `next` token.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
) (instance aastypes.{interface_name},
{I}next xml.Token,
{I}err error,
) {{
{I}{indent_but_first_line(initialization, I)}

{I}for {{
{II}var local string
{II}var ok bool
{II}local, current, ok, err = nextProperty(decoder, current, {interface_name_literal})
{II}if err != nil {{
{III}return
{II}}}
{II}if !ok {{
{III}break
{II}}}

{II}{indent_but_first_line(switch_snippet, II)}

{II}current, err = concludeProperty(decoder, current, local, valueErr)
{II}if err != nil {{
{III}return
{II}}}
{I}}}

{I}next = current

{I}{indent_but_first_line(construct, I)}
{I}return
}}"""
    )


def _generate_read_dispatched(
    our_type: Union[intermediate.ClassUnion, intermediate.NamedUnion]
) -> Stripped:
    """
    Generate the function to read an instance of ``our_type`` by its element name.

    An instance element is self-describing: its local name *is* its type. This one
    function covers every such case -- an abstract class dispatches over its concrete
    descendants, a concrete class over its concrete descendants and itself, and
    a named union over its implementers. A concrete class without concrete descendants
    thus degenerates to a single alternative, which is still worth a function: it is
    what lets [readListOf] and the ``readTuple*`` functions read an item without
    knowing anything about it.

    The element framing is deliberately *not* part of the generated function. It lives
    in ``readElementDispatched`` alone (see
    :py:func:`_generate_read_element_dispatched`), which every container delegates to.
    """
    if isinstance(our_type, intermediate.NamedUnion):
        alternatives = list(
            our_type.implementers
        )  # type: List[intermediate.ConcreteClass]
        union_name = golang_naming.union_name(our_type.name)
        value_type = Stripped(f"*aastypes.{union_name}")
        doc_reference = Stripped(f"aastypes.{union_name}")
        default_error = Stripped(
            f"unexpectedDiscriminator(local, "
            f"{golang_common.string_literal(f'the union {union_name}')})"
        )
    else:
        alternatives = list(our_type.concrete_descendants)
        if isinstance(our_type, intermediate.ConcreteClass):
            alternatives.append(our_type)

        interface_name = golang_naming.interface_name(our_type.name)
        value_type = Stripped(f"aastypes.{interface_name}")
        doc_reference = Stripped(f"aastypes.{interface_name}")

        if isinstance(our_type, intermediate.ConcreteClass) and (
            len(our_type.concrete_descendants) == 0
        ):
            # NOTE (mristin):
            # There is only a single alternative, so naming it in the error message
            # is more informative than pointing at a discriminator which does not
            # actually discriminate anything.
            default_error = Stripped(
                f"unexpectedStartElement(local, "
                f"{golang_common.string_literal(naming.xml_class_name(our_type.name))})"
            )
        else:
            default_error = Stripped(
                f"unexpectedDiscriminator(local, "
                f"{golang_common.string_literal(interface_name)})"
            )

    case_blocks = []  # type: List[Stripped]

    for alternative in alternatives:
        xml_class_name_literal = golang_common.string_literal(
            naming.xml_class_name(alternative.name)
        )
        read_as_sequence = golang_naming.private_function_name(
            Identifier(f"read_{alternative.name}_as_sequence")
        )

        if isinstance(our_type, intermediate.NamedUnion):
            alternative_interface_name = golang_naming.interface_name(alternative.name)
            from_function_name = golang_naming.function_name(
                Identifier(f"new_{our_type.name}_from_{alternative.name}")
            )

            case_blocks.append(
                Stripped(
                    f"""\
case {xml_class_name_literal}:
{I}var casted aastypes.{alternative_interface_name}
{I}casted, next, err = {read_as_sequence}(decoder, current)
{I}if err == nil {{
{II}instance = aastypes.{from_function_name}(casted)
{I}}}"""
                )
            )
        else:
            case_blocks.append(
                Stripped(
                    f"""\
case {xml_class_name_literal}:
{I}instance, next, err = {read_as_sequence}(decoder, current)"""
                )
            )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = {default_error}"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    function_name = golang_naming.private_function_name(
        Identifier(f"read_{our_type.name}_dispatched")
    )

    return Stripped(
        f"""\
// De-serialize an instance of [{doc_reference}] based on the `local` name
// of its start element.
//
// The `current` token is expected to point to the content of that start element, and
// the resulting `next` token points to its end element.
func {function_name}(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (instance {value_type},
{I}next xml.Token,
{I}err error,
) {{
{I}switch local {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
{I}return
}}"""
    )


def _generate_read_class_dispatched(symbol_table: intermediate.SymbolTable) -> Stripped:
    """Generate the function to read any instance by its element name."""
    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        read_as_sequence = golang_naming.private_function_name(
            Identifier(f"read_{cls.name}_as_sequence")
        )

        xml_class_name_literal = golang_common.string_literal(
            naming.xml_class_name(cls.name)
        )

        case_blocks.append(
            Stripped(
                f"""\
case {xml_class_name_literal}:
{I}instance, next, err = {read_as_sequence}(decoder, current)"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newDeserializationError(
{II}fmt.Sprintf(
{III}"Unexpected XML element name %s as class discriminator",
{III}local,
{II}),
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)

    return Stripped(
        f"""\
// De-serialize an instance of [aastypes.IClass] based on the `local` name
// of its start element.
//
// The `current` token is expected to point to the content of that start element, and
// the resulting `next` token points to its end element.
func readClassDispatched(
{I}decoder *xml.Decoder,
{I}current xml.Token,
{I}local string,
) (instance aastypes.IClass,
{I}next xml.Token,
{I}err error,
) {{
{I}switch local {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
{I}return
}}"""
    )


def _generate_unmarshal() -> Stripped:
    return Stripped(
        f"""\
// Unmarshal an instance of [aastypes.IClass] serialized as an XML element.
//
// The XML element must live in the [Namespace] space.
func Unmarshal(
{I}decoder *xml.Decoder,
) (instance aastypes.IClass, err error) {{
{I}var current xml.Token
{I}current, err = readNext(decoder, nil)
{I}if err != nil {{
{II}return
{I}}}

{I}instance, _, err = readElementDispatched(
{II}decoder, current, readClassDispatched,
{I})
{I}return
}}"""
    )


# endregion

# region Serialization


def _generate_serialization_error() -> List[Stripped]:
    return [
        Stripped(
            f"""\
// Represent an error during the serialization.
//
// Implements `error`.
type SerializationError struct {{
{I}Path    *aasreporting.Path
{I}Message string
}}"""
        ),
        Stripped(
            f"""\
func newSerializationError(message string) *SerializationError {{
{I}return &SerializationError{{
{II}Path:    &aasreporting.Path{{}},
{II}Message: message,
{I}}}
}}"""
        ),
        Stripped(
            f"""\
func (se *SerializationError) Error() string {{
{I}return fmt.Sprintf(
{II}"%s: %s",
{II}se.PathString(),
{II}se.Message,
{I})
}}"""
        ),
        Stripped(
            f"""\
// Render the path as a string.
func (se *SerializationError) PathString() string {{
{I}return aasreporting.ToGolangPath(se.Path)
}}"""
        ),
    ]


def _generate_write_start_element() -> Stripped:
    return Stripped(
        f"""\
// Write the start element with the given `local` name to the encoder.
//
// Do not flush.
//
// If the `withNamespace` is set, set the [xml.Name.Space] property in the element
// accordingly.
func writeStartElement(
{I}encoder *xml.Encoder,
{I}local string,
{I}withNamespace bool,
) (err error) {{
{I}startElement := xml.StartElement{{Name: xml.Name{{Local: local}}}}
{I}if withNamespace {{
{II}startElement.Name.Space = Namespace
{I}}}

{I}err = encoder.EncodeToken(startElement)
{I}return
}}"""
    )


def _generate_write_end_element() -> Stripped:
    return Stripped(
        f"""\
// Write the end element with the given `local` name to the encoder.
//
// Do not flush.
//
// If the `withNamespace` is set, set the [xml.Name.Space] property in the element
// accordingly.
func writeEndElement(
{I}encoder *xml.Encoder,
{I}local string,
{I}withNamespace bool,
) (err error) {{
{I}endElement := xml.EndElement{{Name: xml.Name{{Local: local}}}}
{I}if withNamespace {{
{II}endElement.Name.Space = Namespace
{I}}}

{I}err = encoder.EncodeToken(endElement)
{I}return
}}"""
    )


def _generate_write_text() -> Stripped:
    return Stripped(
        f"""\
// Write the `text` to the encoder.
//
// Do not flush.
//
// If `text` is empty, do nothing.
func writeText(
{I}encoder *xml.Encoder,
{I}text string,
) (err error) {{
{I}if len(text) > 0 {{
{II}err = encoder.EncodeToken(
{III}xml.CharData([]byte(text)),
{II})
{I}}}
{I}return
}}"""
    )


def _generate_write_as_text_bool() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:boolean` in a text element.
//
// Do not flush.
func writeAsText_bool(
{I}encoder *xml.Encoder,
{I}value bool,
) (err error) {{
{I}text := "true"
{I}if !value {{
{II}text = "false"
{I}}}
{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_as_text_long() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:long` in a text element.
//
// Do not flush.
func writeAsText_long(
{I}encoder *xml.Encoder,
{I}value int64,
) (err error) {{
{I}text := strconv.FormatInt(value, 10)
{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_as_text_double() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:double` in a text element.
//
// Do not flush.
func writeAsText_double(
{I}encoder *xml.Encoder,
{I}value float64,
) (err error) {{
{I}var text string

{I}// See: https://www.w3.org/TR/xmlschema-2/#double
{I}// for the exact literals.
{I}if math.IsInf(value, 0) {{
{II}if value < 0 {{
{III}text = "-INF"
{II}}} else {{
{III}text = "INF"
{II}}}
{I}}} else if math.IsNaN(value) {{
{II}text = "NaN"
{I}}} else {{
{II}text = strconv.FormatFloat(value, 'g', -1, 64)
{I}}}

{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_as_text_string() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a `xs:string` in a text element.
//
// Do not flush.
func writeAsText_string(
{I}encoder *xml.Encoder,
{I}value string,
) (err error) {{
{I}err = writeText(encoder, value)
{I}return
}}"""
    )


def _generate_write_as_text_bytes() -> Stripped:
    return Stripped(
        f"""\
// Write the `value` as a base64-encoded bytes in a text element.
//
// Do not flush.
func writeAsText_bytes(
{I}encoder *xml.Encoder,
{I}value []byte,
) (err error) {{
{I}text := b64.StdEncoding.EncodeToString(
{II}value,
{I})

{I}err = writeText(encoder, text)
{I}return
}}"""
    )


def _generate_write_element() -> Stripped:
    """
    Generate the single function which frames an XML element around a value.

    Everything else in the serialization only decides *what* is written --
    the framing itself lives here, so that a property, a list item and
    a tuple item differ solely in the given content writer. An optional
    property goes through the ``writeOptional*`` family instead, which
    calls this function only if the value is set.
    """
    return Stripped(
        f"""\
// Write `that` as an XML element with the `local` name, its content written by
// `writeContent`.
//
// Do not flush.
//
// This is the one place which frames an XML element around a *value*: a property,
// a list item and a tuple item all go through it, and differ only in the given
// `writeContent`. A list frames its own element in [writeList], and an instance
// the element naming its model type in [writeClassElement], as neither of the two
// can be reduced to a content writer without allocating a closure.
//
// The XML namespace is expected to have been defined outside of the resulting XML
// element.
func writeElement[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}that T,
{I}writeContent func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}err = writeStartElement(encoder, local, false)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeContent(encoder, that)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeEndElement(encoder, local, false)
{I}return
}}"""
    )


def _generate_write_optional_pointer() -> Stripped:
    """
    Generate the writer of an optional value represented as a pointer.

    This is the first of the ``writeOptional*`` family. There is one member
    per way Golang spells an optional -- each named after that spelling,
    since the check for the presence, and *only* it, is what differs between
    them: a pointer here, a value which is nil on its own in
    :py:func:`_generate_write_optional_instance` and a slice in
    :py:func:`_generate_write_optional_slice`.

    The three can not be collapsed into one. Golang decides ``nil``-ness by
    the representation: a type parameter can not be compared against
    ``nil`` at all, ``any(that) == nil`` is false for a nil *pointer* boxed
    in an ``any``, and comparing against the zero value of a type parameter
    panics on a slice, which is not comparable. Nor can the write be handed
    over as its *result*, the way a read is handed to ``readOptional``:
    Golang would already have performed it.

    They are worth having nevertheless. An ``if value := that.X(); value !=
    nil`` at the call site would indeed decide all four at once, as the type
    is concrete there, but it names the value twice and does not compose
    into the single ``finishProperty`` expression -- so a property would no
    longer be written by one call whether it is optional or not.
    """
    return Stripped(
        f"""\
// Write the optional `that` as an XML element with the `local` name, or write
// nothing at all if it is not set.
//
// Do not flush.
//
// A scalar and a tuple are not nilable in Golang, so an optional one is represented
// as a pointer. The pointer is dereferenced here, so that `writeContent` sees only
// the value. See also [writeOptionalInstance] and [writeOptionalSlice], which differ
// from this function only in how the presence is decided.
func writeOptionalPointer[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}that *T,
{I}writeContent func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}if that == nil {{
{II}return
{I}}}

{I}return writeElement(encoder, local, *that, writeContent)
}}"""
    )


def _generate_write_optional_instance() -> Stripped:
    """Generate the writer of an optional value which is nil on its own."""
    return Stripped(
        f"""\
// Write the optional instance `that` as an XML element with the `local` name, or
// write nothing at all if it is not set.
//
// Do not flush.
//
// An instance is represented as an interface and a named union as a pointer to
// a struct, both of which are nil on their own, so -- unlike in [writeOptionalPointer] --
// there is no pointer to dereference.
//
// Golang does not allow a value of a type parameter to be compared against `nil`,
// and `any(that) == nil` would not do either: a nil *pointer* converted to `any` is
// a non-nil `any` which carries the type of that pointer. Comparing against
// the zero value of `T` covers both, as it compares nil against nil for
// an interface, and a nil pointer against a nil pointer of the same type for
// a named union.
func writeOptionalInstance[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}that T,
{I}writeContent func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}var unset T
{I}if any(that) == any(unset) {{
{II}return
{I}}}

{I}return writeElement(encoder, local, that, writeContent)
}}"""
    )


def _generate_write_optional_slice() -> Stripped:
    """Generate the writer of an optional slice, nil on its own."""
    return Stripped(
        f"""\
// Write the optional `that` as an XML element with the `local` name, or write
// nothing at all if it is not set.
//
// Do not flush.
//
// A list and the bytes are represented as a slice, which is nil on its own, but --
// unlike an instance in [writeOptionalInstance] -- can not be compared against
// the zero value, as a slice is not comparable at all. Mind that a nil slice and
// an empty slice differ here: only the former is considered absent, while
// the latter is written as an empty XML element.
func writeOptionalSlice[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}that []T,
{I}writeContent func(anEncoder *xml.Encoder, aValue []T) (anErr error),
) (err error) {{
{I}if that == nil {{
{II}return
{I}}}

{I}return writeElement(encoder, local, that, writeContent)
}}"""
    )


def _generate_write_list() -> Stripped:
    """Generate the writer of the items of a list."""
    return Stripped(
        f"""\
// Write the items of the `list`, each as an XML element of its own.
//
// Do not flush.
//
// The element *around* the list is framed by whoever writes the list, see
// the generated `writeListOf*` functions. Every item frames its own element
// through `writeItem`: an instance is written as an element named after its model
// type, while a scalar is wrapped in the element `v`. A list of instances and
// a list of scalars therefore share this one function.
func writeList[T any](
{I}encoder *xml.Encoder,
{I}list []T,
{I}writeItem func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}for i, item := range list {{
{II}err = writeItem(encoder, item)
{II}if err != nil {{
{III}if seriaErr, ok := err.(*SerializationError); ok {{
{IIII}seriaErr.Path.PrependIndex(
{IIIII}&aasreporting.IndexSegment{{Index: i}},
{IIII})
{III}}}
{III}return
{II}}}
{I}}}

{I}return
}}"""
    )


def _generate_finish_property() -> Stripped:
    """Generate the function concluding the writing of a single property."""
    return Stripped(
        f"""\
// Conclude the writing of the property read by `getter` by attributing the error,
// if any, to that property.
//
// Do not flush.
//
// `getter` is the getter of the property *as it is spelled in Golang*, `Value()`
// and not `value`, since it is prepended to the path of a serialization error,
// which [SerializationError.PathString] renders as a Golang expression through
// [aasreporting.ToGolangPath]. (Golang has no way to name a member at compile time,
// so the getter has to be spelled out; mind that the de-serialization reports
// an XPath instead, and hence prepends the XML name there.)
//
// The write itself is given as its *result*, not as a function to be called, so that
// this one function concludes every property, no matter which of the `write*`
// functions wrote it, and no matter how many arguments that function took. Golang
// evaluates the argument, hence performs the write, before this call.
func finishProperty(
{I}getter string,
{I}err error,
) error {{
{I}if err != nil {{
{II}if seriaErr, ok := err.(*SerializationError); ok {{
{III}seriaErr.Path.PrependName(
{IIII}&aasreporting.NameSegment{{Name: getter}},
{III})
{II}}}
{II}return err
{I}}}

{I}return nil
}}"""
    )


def _generate_write_instance() -> Stripped:
    """Generate the content writer of an instance written as its own element."""
    return Stripped(
        f"""\
// Write the instance `that` as an XML element named after its model type.
//
// Do not flush.
//
// This is the content writer of every instance which is not embedded in the element
// of its property, be it a property, a list item or a tuple item: [Marshal] picks
// the element name from the runtime model type.
//
// Golang function values are invariant in their parameter type, so [Marshal], which
// takes the wide [aastypes.IClass], can not be used where a writer of a more
// specific interface is expected -- this generic function exists solely to narrow
// the parameter type to `T`. Golang can not infer `T` from the context here, so
// every call site instantiates it explicitly, *e.g.*,
// `writeInstance[aastypes.IReference]`, and passes it on as that instantiated
// function value, without a closure.
func writeInstance[T aastypes.IClass](
{I}encoder *xml.Encoder,
{I}that T,
) error {{
{I}return writeClass(encoder, that, false)
}}"""
    )


def _generate_named_union_constraint() -> Stripped:
    """
    Generate the constraint interface shared by the named-union writers.

    A named union is deliberately not an ``aastypes.IClass``, but every
    named union exposes its underlying instance through ``Underlying`` --
    constraining a generic type parameter to that single method lets one
    writer serve every named union, instead of generating one dedicated,
    non-generic writer per union.
    """
    return Stripped(
        f"""\
// Constrain a generic type to a named union, giving access to its
// underlying instance for serialization.
type namedUnion interface {{
{I}Underlying() aastypes.IClass
}}"""
    )


def _generate_write_union() -> Stripped:
    """Generate the content writer of a named union."""
    return Stripped(
        f"""\
// Write the named union `that` as the XML element of its underlying instance.
//
// Do not flush.
//
// A named union is deliberately not an [aastypes.IClass], so [writeInstance] can not
// serve it; this writer narrows through the [namedUnion] constraint instead, and one
// generic writer thus covers every named union.
//
// Do not flush.
func writeUnion[T namedUnion](
{I}encoder *xml.Encoder,
{I}that T,
) error {{
{I}return writeClass(encoder, that.Underlying(), false)
}}"""
    )


@require(lambda arity: arity > 0)
def _generate_write_tuple_helper(arity: int) -> Stripped:
    """Generate a generic function to write the items of a tuple of ``arity``."""
    type_params = [f"T{i + 1}" for i in range(arity)]
    type_params_joined = ", ".join(f"{t} any" for t in type_params)

    tuple_type = f"aascommon.Tuple{arity}[{', '.join(type_params)}]"

    params_joined = ",\n".join(
        f"writeItem{i + 1} func(encoder *xml.Encoder, value {type_params[i]}) error"
        for i in range(arity)
    )

    item_blocks = []  # type: List[Stripped]
    for i in range(arity):
        item_blocks.append(
            Stripped(
                f"""\
err = writeItem{i + 1}(encoder, that.Item{i + 1})
if err != nil {{
{I}if seriaErr, ok := err.(*SerializationError); ok {{
{II}seriaErr.Path.PrependIndex(
{III}&aasreporting.IndexSegment{{Index: {i}}},
{II})
{I}}}
{I}return
}}"""
            )
        )

    item_blocks_joined = "\n\n".join(item_blocks)

    function_name = f"writeTuple{arity}"

    return Stripped(
        f"""\
// Write `that` with `writeItem1`, `writeItem2`, *etc.* on the
// correspondingly positioned item, or return an error.
//
// Do not flush.
//
// Every item writes its own element, so this function is shared by every tuple of
// arity {arity}, whichever mix of scalar and instance items it holds.
func {function_name}[{type_params_joined}](
{I}encoder *xml.Encoder,
{I}that {tuple_type},
{I}{indent_but_first_line(params_joined, I)},
) (err error) {{
{I}{indent_but_first_line(item_blocks_joined, I)}

{I}return
}}"""
    )


def _generate_write_class_element() -> Stripped:
    """Generate the function writing an instance as the element of its class."""
    return Stripped(
        f"""\
// Write `that` as an XML element with the `local` name representing its model type.
//
// Do not flush.
//
// If `withNamespace` is set, the `xmlns` attribute is set in the outer XML element.
//
// Unlike [writeElement], which frames a *property*, this function frames an instance
// in the element which discriminates its model type, and is therefore the one place
// where the XML namespace can be set.
func writeClassElement[T any](
{I}encoder *xml.Encoder,
{I}local string,
{I}withNamespace bool,
{I}that T,
{I}writeTAsSequence func(anEncoder *xml.Encoder, aValue T) (anErr error),
) (err error) {{
{I}err = writeStartElement(encoder, local, withNamespace)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeTAsSequence(encoder, that)
{I}if err != nil {{
{II}return
{I}}}

{I}err = writeEndElement(encoder, local, withNamespace)
{I}return
}}"""
    )


def _generate_write_enumeration_as_text(
    enumeration: intermediate.Enumeration,
) -> Stripped:
    enum_name = golang_naming.enum_name(enumeration.name)
    function_name = _enum_text_writer_name(enumeration)
    to_string_name = golang_naming.function_name(
        Identifier(f"{enumeration.name}_to_string")
    )

    return Stripped(
        f"""\
// Write the `value` of a property as string representation
// of [aastypes.{enum_name}]
// in a text element.
//
// Do not flush.
func {function_name}(
{I}encoder *xml.Encoder,
{I}value aastypes.{enum_name},
) (err error) {{
{I}text, ok := aasstringification.{to_string_name}(
{II}value,
{I})
{I}if !ok {{
{II}err = newSerializationError(
{III}fmt.Sprintf(
{IIII}"Unexpected literal of {enum_name}: %v",
{IIII}value,
{III}),
{II})
{II}return
{I}}}

{I}err = writeText(encoder, text)
{I}return
}}"""
    )


_WRITE_FUNCTION_BY_PRIMITIVE_TYPE = {
    intermediate.PrimitiveType.BOOL: "writeAsText_bool",
    intermediate.PrimitiveType.INT: "writeAsText_long",
    intermediate.PrimitiveType.FLOAT: "writeAsText_double",
    intermediate.PrimitiveType.STR: "writeAsText_string",
    intermediate.PrimitiveType.BYTEARRAY: "writeAsText_bytes",
}
assert all(
    literal in _WRITE_FUNCTION_BY_PRIMITIVE_TYPE
    for literal in intermediate.PrimitiveType
)


def _write_text_function(type_anno: intermediate.AtomicTypeAnnotation) -> Stripped:
    """Determine the function which writes a scalar ``type_anno`` as text."""
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Stripped(_WRITE_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])

    assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
        type_anno.our_type, intermediate.Enumeration
    ), (
        f"Expected a scalar type annotation, but got {type_anno}; "
        f"the instances are written as their own element instead"
    )

    return Stripped(_enum_text_writer_name(type_anno.our_type))


def _generate_write_scalar_item(scalar_item: _ScalarItem) -> Stripped:
    """Generate the function to write a scalar item in a fixed element name."""
    function_name = _scalar_item_writer_name(
        scalar_item.type_anno, scalar_item.element_name
    )

    value_type = golang_common.generate_type(
        type_annotation=scalar_item.type_anno, types_package=Identifier("aastypes")
    )

    element_name_literal = golang_common.string_literal(scalar_item.element_name)

    arguments_joined = golang_common.join_arguments(
        [
            "encoder",
            element_name_literal,
            "value",
            _write_text_function(scalar_item.type_anno),
        ],
        indention=2,
    )

    return Stripped(
        f"""\
// Write the scalar `value` in the element `{scalar_item.element_name}`.
//
// Do not flush.
func {function_name}(
{I}encoder *xml.Encoder,
{I}value {value_type},
) error {{
{I}return writeElement(
{II}{indent_but_first_line(arguments_joined, II)}
{I})
}}"""
    )


def _item_writer_expr(
    type_anno: intermediate.AtomicTypeAnnotation, element_name: str
) -> Stripped:
    """
    Determine the writer of an item of ``type_anno`` in a list or in a tuple.

    An instance and a named union write their own, self-describing element, so
    ``element_name`` is disregarded for them.
    """
    if isinstance(type_anno, intermediate.OurTypeAnnotation):
        our_type = type_anno.our_type

        item_type = golang_common.generate_type(
            type_annotation=type_anno, types_package=Identifier("aastypes")
        )

        if isinstance(
            our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
        ):
            return Stripped(f"writeInstance[{item_type}]")

        if isinstance(our_type, intermediate.NamedUnion):
            return Stripped(f"writeUnion[{item_type}]")

    return Stripped(_scalar_item_writer_name(type_anno, element_name))


def _generate_write_list_content_writer(
    items_type_anno: intermediate.AtomicTypeAnnotation,
) -> Stripped:
    """
    Generate the writer of the content of a list of ``items_type_anno``.

    ``writeList`` takes the writer of a single item, so it can not be passed on
    as a content writer itself -- and Golang gives no partial application which
    would bind that item writer in without allocating a closure. This function
    binds it at the package level instead, so that a list is written by exactly
    the same call as any other value, be it optional or not.
    """
    items_type = golang_common.generate_type(
        type_annotation=items_type_anno, types_package=Identifier("aastypes")
    )

    arguments_joined = golang_common.join_arguments(
        ["encoder", "list", _item_writer_expr(items_type_anno, "v")], indention=2
    )

    return Stripped(
        f"""\
// Write the items of the `list` as a sequence of XML elements.
//
// Do not flush.
func {_list_content_writer_name(items_type_anno)}(
{I}encoder *xml.Encoder,
{I}list []{items_type},
) error {{
{I}return writeList(
{II}{indent_but_first_line(arguments_joined, II)}
{I})
}}"""
    )


def _generate_write_tuple_content_writer(
    type_anno: intermediate.TupleTypeAnnotation,
) -> Stripped:
    """
    Generate the writer of the content of a tuple.

    A ``writeTuple*`` takes an item writer per item, so it can not be passed on
    as a content writer itself -- and Golang gives no partial application which
    would bind those item writers in without allocating a closure. This function
    binds them at the package level instead, so that a tuple is written by exactly
    the same call as any other value, be it optional or not.
    """
    tuple_type = golang_common.generate_type(
        type_annotation=type_anno, types_package=Identifier("aastypes")
    )

    item_writer_exprs = []  # type: List[Stripped]
    for i, item_type_anno in enumerate(type_anno.items):
        assert isinstance(item_type_anno, intermediate.AtomicTypeAnnotationAsTuple)
        item_writer_exprs.append(_item_writer_expr(item_type_anno, f"v{i + 1}"))

    arguments_joined = golang_common.join_arguments(
        ["encoder", "that", *item_writer_exprs], indention=2
    )

    return Stripped(
        f"""\
// Write the items of `that` as a sequence of XML elements.
//
// Do not flush.
func {_tuple_content_writer_name(type_anno)}(
{I}encoder *xml.Encoder,
{I}that {tuple_type},
) error {{
{I}return writeTuple{len(type_anno.items)}(
{II}{indent_but_first_line(arguments_joined, II)}
{I})
}}"""
    )


def _content_writer_expr(type_anno: intermediate.TypeAnnotationUnion) -> Stripped:
    """
    Determine the writer of the content of an XML element holding ``type_anno``.

    Mind the difference to :py:func:`_item_writer_expr`: an instance embedded in
    the element of its property writes only its sequence of properties, while
    an item of a list or of a tuple writes its own element on top of it.
    """
    primitive_type = intermediate.try_primitive_type(type_anno)
    if primitive_type is not None:
        return Stripped(_WRITE_FUNCTION_BY_PRIMITIVE_TYPE[primitive_type])

    if isinstance(type_anno, intermediate.ListTypeAnnotation):
        assert isinstance(type_anno.items, intermediate.AtomicTypeAnnotationAsTuple)
        return _list_content_writer_name(type_anno.items)

    if isinstance(type_anno, intermediate.TupleTypeAnnotation):
        return _tuple_content_writer_name(type_anno)

    assert isinstance(
        type_anno, intermediate.OurTypeAnnotation
    ), f"Unexpected type annotation for a content writer: {type_anno}"

    our_type = type_anno.our_type

    if isinstance(our_type, intermediate.Enumeration):
        return _write_text_function(type_anno)

    golang_type = golang_common.generate_type(
        type_annotation=type_anno, types_package=Identifier("aastypes")
    )

    if isinstance(our_type, intermediate.NamedUnion):
        return Stripped(f"writeUnion[{golang_type}]")

    assert isinstance(
        our_type, (intermediate.AbstractClass, intermediate.ConcreteClass)
    ), f"Unexpected our type for a content writer: {our_type}"

    if _requires_dispatch(type_anno):
        return Stripped(f"writeInstance[{golang_type}]")

    # NOTE (mristin):
    # A concrete class without any concrete descendant is embedded directly in
    # the element of its property, so its sequence of properties *is* the content.
    return Stripped(
        golang_naming.private_function_name(
            Identifier(f"write_{our_type.name}_as_sequence")
        )
    )


def _wrap_in_finish_property(getter_name: Identifier, write_expr: Stripped) -> Stripped:
    """
    Conclude the ``write_expr`` of the property with the given ``getter_name``.

    The getter is spelled out as a call, ``SemanticID()``, since that is how
    the path of a serialization error is reported back to the user -- as a Golang
    expression, not as an XML name.
    """
    getter_literal = golang_common.string_literal(f"{getter_name}()")

    return Stripped(
        f"""\
err = finishProperty(
{I}{getter_literal},
{I}{indent_but_first_line(write_expr, I)},
)
if err != nil {{
{I}return
}}"""
    )


@require(lambda prop, cls: id(prop) in cls.property_id_set)
def _generate_snippet_to_serialize_property(
    prop: intermediate.Property, cls: intermediate.ConcreteClass
) -> Tuple[Optional[Stripped], Optional[Error]]:
    """
    Generate the snippet to serialize the property ``prop``.

    Every property is written by the same call and concluded by the same
    ``finishProperty``; only the entry point -- which decides on the presence of
    an optional, see :py:func:`_generate_write_optional` -- and the content writer
    differ.
    """
    type_anno = intermediate.beneath_optional(prop.type_annotation)

    if isinstance(type_anno, intermediate.ListTypeAnnotation) and not isinstance(
        type_anno.items, intermediate.AtomicTypeAnnotationAsTuple
    ):
        return None, Error(
            prop.parsed.node,
            f"(mristin) We only handle the XML serialization of lists of "
            f"atomic values, but you want to generate the code for a list of "
            f"type {type_anno}. Please contact the developers if you need "
            f"this feature.",
        )

    optional = isinstance(prop.type_annotation, intermediate.OptionalTypeAnnotation)

    if not optional:
        function_name = "writeElement"
    elif golang_pointering.is_pointer_type(prop.type_annotation):
        function_name = "writeOptionalPointer"
    elif isinstance(
        type_anno, intermediate.ListTypeAnnotation
    ) or intermediate.try_primitive_type(type_anno) is (
        intermediate.PrimitiveType.BYTEARRAY
    ):
        function_name = "writeOptionalSlice"
    else:
        assert isinstance(type_anno, intermediate.OurTypeAnnotation) and isinstance(
            type_anno.our_type,
            (
                intermediate.AbstractClass,
                intermediate.ConcreteClass,
                intermediate.NamedUnion,
            ),
        ), (
            f"Expected an instance or a named union, the only optionals which are "
            f"nil on their own, but got {type_anno}; mind that "
            f"``writeOptionalInstance`` compares against the zero value, which "
            f"panics at runtime on a slice"
        )

        function_name = "writeOptionalInstance"

    getter_name = golang_naming.getter_name(prop.name)

    arguments_joined = golang_common.join_arguments(
        [
            "encoder",
            golang_common.string_literal(prop.xml_name),
            f"that.{getter_name}()",
            _content_writer_expr(type_anno),
        ],
        indention=3,
    )

    return (
        _wrap_in_finish_property(
            getter_name=getter_name,
            write_expr=Stripped(
                f"""\
{function_name}(
{I}{indent_but_first_line(arguments_joined, I)}
)"""
            ),
        ),
        None,
    )


def _generate_write_as_sequence(
    cls: intermediate.ConcreteClass,
) -> Tuple[Optional[Stripped], Optional[List[Error]]]:
    function_name = golang_naming.private_function_name(
        Identifier(f"write_{cls.name}_as_sequence")
    )

    interface_name = golang_naming.interface_name(cls.name)

    prop_blocks = []  # type: List[Stripped]
    errors = []  # type: List[Error]

    for prop in cls.properties:
        prop_block, error = _generate_snippet_to_serialize_property(prop=prop, cls=cls)
        if error is not None:
            errors.append(error)
            continue

        assert prop_block is not None
        prop_blocks.append(prop_block)

    if len(errors) > 0:
        return None, errors

    if len(prop_blocks) == 0:
        prop_blocks.append(Stripped("// Intentionally empty."))

    prop_blocks_joined = "\n\n".join(prop_blocks)

    return (
        Stripped(
            f"""\
// Serialize the instance
// of [aastypes.{interface_name}]
// as a sequence of properties, each represented as an XML element.
//
// The XML namespace is expected to be set in the one of the parent elements
// enclosing the sequence.
//
// Do not flush.
func {function_name}(
{I}encoder *xml.Encoder,
{I}that aastypes.{interface_name},
) (err error) {{
{I}{indent_but_first_line(prop_blocks_joined, I)}

{I}return
}}"""
        ),
        None,
    )


def _generate_write_class(symbol_table: intermediate.SymbolTable) -> Stripped:
    """
    Generate the function which dispatches on the model type of an instance.

    This is [Marshal] without the flush, so that the flush happens exactly
    once per [Marshal], and not once per instance nested in it.
    """
    case_blocks = []  # type: List[Stripped]
    for cls in symbol_table.concrete_classes:
        model_type_literal = golang_naming.enum_literal_name(
            enumeration_name=Identifier("Model_type"), literal_name=cls.name
        )

        interface_name = golang_naming.interface_name(cls.name)

        xml_class_name_literal = golang_common.string_literal(
            naming.xml_class_name(cls.name)
        )

        write_as_sequence_name = golang_naming.private_function_name(
            Identifier(f"write_{cls.name}_as_sequence")
        )

        arguments_joined = golang_common.join_arguments(
            [
                "encoder",
                xml_class_name_literal,
                "withNamespace",
                f"that.(aastypes.{interface_name})",
                write_as_sequence_name,
            ],
            indention=3,
        )

        case_blocks.append(
            Stripped(
                f"""\
case aastypes.{model_type_literal}:
{I}err = writeClassElement(
{II}{indent_but_first_line(arguments_joined, II)}
{I})"""
            )
        )

    case_blocks.append(
        Stripped(
            f"""\
default:
{I}err = newSerializationError(
{II}fmt.Sprintf(
{III}"Unexpected model type: %v",
{III}that.ModelType(),
{II}),
{I})"""
        )
    )

    case_blocks_joined = "\n".join(case_blocks)
    model_type_getter = golang_naming.getter_name(Identifier("model_type"))

    return Stripped(
        f"""\
// Serialize `that` instance as an XML element named after its model type.
//
// Do not flush.
//
// If `withNamespace` is set, the `xmlns` attribute is set in the XML element
// to [Namespace].
func writeClass(
{I}encoder *xml.Encoder,
{I}that aastypes.IClass,
{I}withNamespace bool,
) (err error) {{
{I}switch that.{model_type_getter}() {{
{I}{indent_but_first_line(case_blocks_joined, I)}
{I}}}
{I}return
}}"""
    )


def _generate_marshal() -> Stripped:
    """
    Generate the public entry point of the serialization.

    Encoding a token does not flush -- [xml.Encoder.EncodeToken] leaves that
    to the caller -- so the encoder has to be flushed exactly once, when
    the whole element has been written. Flushing more often, say after every
    property, only defeats the buffering of the encoder.
    """
    return Stripped(
        f"""\
// Serialize `that` instance as an XML element, and flush the encoder.
//
// If `withNamespace` is set, the `xmlns` attribute is set in the XML element
// to [Namespace].
func Marshal(
{I}encoder *xml.Encoder,
{I}that aastypes.IClass,
{I}withNamespace bool,
) (err error) {{
{I}err = writeClass(encoder, that, withNamespace)
{I}if err != nil {{
{II}return
{I}}}

{I}return encoder.Flush()
}}"""
    )


# endregion

# fmt: off
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(
    lambda result:
    not (result[0] is not None) or result[0].endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(
    symbol_table: intermediate.SymbolTable,
    spec_impls: specific_implementations.SpecificImplementations,
    repo_url: Stripped,
) -> Tuple[Optional[str], Optional[List[Error]]]:
    """Generate code for XML de/serialization."""
    aascommon_url_literal = golang_common.string_literal(f"{repo_url}/common")

    aastypes_url_literal = golang_common.string_literal(f"{repo_url}/types")

    aasreporting_url_literal = golang_common.string_literal(f"{repo_url}/reporting")

    aasstringification_url_literal = golang_common.string_literal(
        f"{repo_url}/stringification"
    )

    namespace_literal = golang_common.string_literal(
        symbol_table.meta_model.xml_namespace
    )

    blocks = [
        Stripped(
            """\
// Package xmlization de/serializes model instances to and from XML.
//
// To de-serialize, call one of the `Unmarshal*` functions.
//
// To serialize, call the [Marshal] function.
package xmlization"""
        ),
        golang_common.WARNING,
        Stripped(
            f"""\
import (
{I}b64 "encoding/base64"
{I}"encoding/xml"
{I}"fmt"
{I}"io"
{I}"math"
{I}"regexp"
{I}"strconv"
{I}"strings"
{I}"unicode"
{I}aascommon {aascommon_url_literal}
{I}aasreporting {aasreporting_url_literal}
{I}aasstringification {aasstringification_url_literal}
{I}aastypes {aastypes_url_literal}
)"""
        ),
        Stripped("// region De-serialization"),
    ]

    blocks.extend(_generate_deserialization_error_and_its_methods())

    blocks.extend(
        [
            Stripped(
                """\
// This is class for a sentinel token to signal the end-of-file.
type eof struct{}"""
            ),
            _generate_is_whitespace(),
            _generate_read_next(),
            _generate_skip_empty_text_whitespace_and_comments(),
            _generate_read_text(),
            _generate_read_text_as_bool(),
            _generate_read_text_as_long(),
            *_generate_is_valid_xs_double(),
            _generate_read_text_as_double(),
            _generate_read_text_as_bytes(),
            Stripped(
                f"""\
const Namespace = {namespace_literal}"""
            ),
            _generate_check_start_element(),
            _generate_extract_local_name_from_start_element(),
            _generate_parse_as_start_element_and_extract_local_name(),
            _generate_check_end_element(),
            *_generate_error_constructors(),
            _generate_read_element_dispatched(),
            _generate_read_list_of(),
            _generate_read_optional(),
            _generate_next_property(),
            _generate_conclude_property(),
        ]
    )

    requirements = _collect_requirements(symbol_table)

    for scalar_item in requirements.scalar_items:
        blocks.append(_generate_read_scalar_item(scalar_item=scalar_item))

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_read_tuple_helper(arity))

    errors = []  # type: List[Error]

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_read_text_as_enumeration(enumeration=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            pass
        elif isinstance(our_type, intermediate.AbstractClass):
            if id(our_type) in requirements.dispatched_type_ids:
                blocks.append(_generate_read_dispatched(our_type=our_type))

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/read_{our_type.name}_as_sequence.go"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue
            else:
                blocks.append(_generate_read_as_sequence(cls=our_type))

            if id(our_type) in requirements.dispatched_type_ids:
                blocks.append(_generate_read_dispatched(our_type=our_type))

        elif isinstance(our_type, intermediate.NamedUnion):
            if id(our_type) in requirements.dispatched_type_ids:
                blocks.append(_generate_read_dispatched(our_type=our_type))

        else:
            assert_never(our_type)

    blocks.append(_generate_read_class_dispatched(symbol_table=symbol_table))

    blocks.append(_generate_unmarshal())

    blocks.append(Stripped("// endregion"))

    blocks.append(Stripped("// region Serialization"))

    blocks.extend(_generate_serialization_error())

    blocks.extend(
        [
            _generate_write_start_element(),
            _generate_write_end_element(),
            _generate_write_text(),
            _generate_write_as_text_bool(),
            _generate_write_as_text_long(),
            _generate_write_as_text_double(),
            _generate_write_as_text_string(),
            _generate_write_as_text_bytes(),
            _generate_write_element(),
            _generate_write_optional_pointer(),
            _generate_write_optional_instance(),
            _generate_write_optional_slice(),
            _generate_write_list(),
            _generate_finish_property(),
            _generate_write_instance(),
            _generate_write_class_element(),
        ]
    )

    if len(symbol_table.named_unions) > 0:
        blocks.append(_generate_named_union_constraint())
        blocks.append(_generate_write_union())

    for scalar_item in requirements.scalar_items:
        blocks.append(_generate_write_scalar_item(scalar_item=scalar_item))

    for arity in intermediate.tuple_arities(symbol_table):
        blocks.append(_generate_write_tuple_helper(arity))

    for items_type_anno in requirements.list_items_type_annos:
        blocks.append(
            _generate_write_list_content_writer(items_type_anno=items_type_anno)
        )

    for tuple_type_anno in requirements.tuple_type_annos:
        blocks.append(_generate_write_tuple_content_writer(type_anno=tuple_type_anno))

    for our_type in symbol_table.our_types:
        if isinstance(our_type, intermediate.Enumeration):
            blocks.append(_generate_write_enumeration_as_text(enumeration=our_type))

        elif isinstance(our_type, intermediate.ConstrainedPrimitive):
            # NOTE (mristin):
            # We will serialize constrained primitives as primitives.
            pass

        elif isinstance(our_type, intermediate.AbstractClass):
            # NOTE (mristin):
            # We will use general ``write`` function.
            pass

        elif isinstance(our_type, intermediate.ConcreteClass):
            if our_type.is_implementation_specific:
                implementation_key = specific_implementations.ImplementationKey(
                    f"Xmlization/write_{our_type.name}_as_sequence.go"
                )

                implementation = spec_impls.get(implementation_key, None)
                if implementation is None:
                    errors.append(
                        Error(
                            our_type.parsed.node,
                            f"The xmlization snippet is missing "
                            f"for the implementation-specific "
                            f"class {our_type.name}: {implementation_key}",
                        )
                    )
                    continue
            else:
                block, block_errors = _generate_write_as_sequence(cls=our_type)
                if block_errors is not None:
                    errors.extend(block_errors)
                    continue

                assert block is not None
                blocks.append(block)

        elif isinstance(our_type, intermediate.NamedUnion):
            # NOTE (mristin):
            # A named union is serialized at its call sites through
            # ``Marshal`` on its underlying instance, so it has no write
            # function of its own.
            pass

        else:
            assert_never(our_type)

    blocks.append(_generate_write_class(symbol_table=symbol_table))

    blocks.append(_generate_marshal())

    blocks.append(Stripped("// endregion"))

    if len(errors) > 0:
        return None, errors

    blocks.append(golang_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue(), None


assert generate.__doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
