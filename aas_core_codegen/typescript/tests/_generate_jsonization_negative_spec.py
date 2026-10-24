"""Generate code for targeted negative JSONization tests."""

import io
from typing import List, Optional, Tuple

from icontract import ensure

from aas_core_codegen import intermediate, naming
from aas_core_codegen.common import Identifier, Stripped
from aas_core_codegen.typescript import common as typescript_common
from aas_core_codegen.typescript import naming as typescript_naming
from aas_core_codegen.typescript.common import INDENT as I


def _first_concrete_class(
    symbol_table: intermediate.SymbolTable,
) -> Optional[intermediate.ConcreteClass]:
    """Select the first concrete class, if any."""
    for concrete_cls in symbol_table.concrete_classes:
        return concrete_cls

    return None


def _first_required_property_candidate(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Tuple[intermediate.ConcreteClass, intermediate.Property]]:
    """Find the first required property among all concrete classes."""
    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            if not isinstance(
                prop.type_annotation, intermediate.OptionalTypeAnnotation
            ):
                return concrete_cls, prop

    return None


def _first_property_for_type_mismatch_candidate(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Tuple[intermediate.ConcreteClass, intermediate.Property, str]]:
    """Find a property where replacing with an object should fail parsing."""
    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)

            if isinstance(type_anno, intermediate.PrimitiveTypeAnnotation):
                file_name = (
                    "minimal.json"
                    if not isinstance(
                        prop.type_annotation,
                        intermediate.OptionalTypeAnnotation,
                    )
                    else "maximal.json"
                )
                return concrete_cls, prop, file_name

            if isinstance(type_anno, intermediate.ListTypeAnnotation):
                file_name = (
                    "minimal.json"
                    if not isinstance(
                        prop.type_annotation,
                        intermediate.OptionalTypeAnnotation,
                    )
                    else "maximal.json"
                )
                return concrete_cls, prop, file_name

            if isinstance(type_anno, intermediate.OurTypeAnnotation):
                if isinstance(
                    type_anno.our_type,
                    (intermediate.AbstractClass, intermediate.ConcreteClass),
                ):
                    continue

                file_name = (
                    "minimal.json"
                    if not isinstance(
                        prop.type_annotation,
                        intermediate.OptionalTypeAnnotation,
                    )
                    else "maximal.json"
                )
                return concrete_cls, prop, file_name

    return None


def _first_nested_class_dispatch_candidate(
    symbol_table: intermediate.SymbolTable,
) -> Optional[Tuple[intermediate.ConcreteClass, intermediate.Property]]:
    """Find a property parsed through class dispatch based on ``modelType``."""
    for concrete_cls in symbol_table.concrete_classes:
        for prop in concrete_cls.properties:
            type_anno = intermediate.beneath_optional(prop.type_annotation)
            if not isinstance(type_anno, intermediate.OurTypeAnnotation):
                continue

            if not isinstance(
                type_anno.our_type,
                (intermediate.AbstractClass, intermediate.ConcreteClass),
            ):
                continue

            if (
                isinstance(type_anno.our_type, intermediate.ConcreteClass)
                and len(type_anno.our_type.concrete_descendants) == 0
            ):
                continue

            return concrete_cls, prop

    return None


# fmt: off
@ensure(
    lambda result: result.endswith('\n'),
    "Trailing newline mandatory for valid end-of-files"
)
# fmt: on
def generate(symbol_table: intermediate.SymbolTable) -> str:
    """Generate code for targeted negative JSONization tests."""
    required_property_candidate = _first_required_property_candidate(symbol_table)
    type_mismatch_candidate = _first_property_for_type_mismatch_candidate(symbol_table)
    nested_dispatch_candidate = _first_nested_class_dispatch_candidate(symbol_table)

    # NOTE (mristin):
    # ``readExpectedJson`` and ``mustBeJsonObject`` are only used by the tests below,
    # which are only generated if a suitable candidate class/property exists in
    # the meta-model. We have to determine that upfront so that we do not define
    # them in vain and trigger an unused-variable lint error on meta-models which do
    # not provide such a candidate (*e.g.*, a class with no properties at all).
    helpers_needed = (
        required_property_candidate is not None
        or type_mismatch_candidate is not None
        or nested_dispatch_candidate is not None
    )

    imports = (
        """\
import * as path from "path";

import * as OurJsonization from "../src/jsonization";

import * as TestCommon from "./common";"""
        if helpers_needed
        else """\
import * as OurJsonization from "../src/jsonization";"""
    )

    blocks: List[Stripped] = [
        Stripped(
            """\
/**
 * Test failure modes in JSON parsing to exercise defensive branches.
 */"""
        ),
        typescript_common.WARNING,
        Stripped(imports),
    ]

    if helpers_needed:
        blocks.append(
            Stripped(
                """\
function readExpectedJson(
    classJsonName: string,
    fileName: "minimal.json" | "maximal.json"
): OurJsonization.JsonValue {
  const pth = path.join(TestCommon.TEST_DATA_DIR, "Json", "Expected", classJsonName, fileName);
  return TestCommon.readJsonFromFileSync(pth);
}

function mustBeJsonObject(jsonable: OurJsonization.JsonValue): OurJsonization.JsonObject {
  if (
    typeof jsonable !== "object" ||
    jsonable === null ||
    typeof jsonable[Symbol.iterator] === "function"
  ) {
    throw new Error(`Expected a JSON object, but got: ${JSON.stringify(jsonable)}`);
  }

  return <OurJsonization.JsonObject>jsonable;
}"""
            )
        )

    first_cls = _first_concrete_class(symbol_table)
    if first_cls is not None:
        deserialization_function = typescript_naming.function_name(
            Identifier(f"{first_cls.name}_from_jsonable")
        )

        blocks.append(
            Stripped(
                f"""\
test("{typescript_naming.class_name(first_cls.name)} deserialization fails on non-object", () => {{
{I}const jsonable = "This is not a JSON object.";

{I}const instanceOrError = OurJsonization.{deserialization_function}(
{I}{I}jsonable
{I});

{I}expect(instanceOrError.error).not.toBeNull();
}});"""
            )
        )

    if required_property_candidate is not None:
        required_cls, required_prop = required_property_candidate
        required_cls_name_json_literal = typescript_common.string_literal(
            naming.json_model_type(required_cls.name)
        )
        required_deserialization_function = typescript_naming.function_name(
            Identifier(f"{required_cls.name}_from_jsonable")
        )
        required_property_name_literal = typescript_common.string_literal(
            required_prop.json_name
        )

        blocks.append(
            Stripped(
                f"""\
test("{typescript_naming.class_name(required_cls.name)} deserialization fails with missing required property", () => {{
{I}const jsonable = readExpectedJson(
{I}{I}{required_cls_name_json_literal},
{I}{I}"minimal.json"
{I});

{I}const jsonObject = {{ ...mustBeJsonObject(jsonable) }};
{I}delete jsonObject[{required_property_name_literal}];

{I}const instanceOrError = OurJsonization.{required_deserialization_function}(
{I}{I}jsonObject
{I});

{I}expect(instanceOrError.error).not.toBeNull();
}});"""
            )
        )

    if type_mismatch_candidate is not None:
        mismatch_cls, mismatch_prop, mismatch_file_name = type_mismatch_candidate
        mismatch_cls_name_json_literal = typescript_common.string_literal(
            naming.json_model_type(mismatch_cls.name)
        )
        mismatch_deserialization_function = typescript_naming.function_name(
            Identifier(f"{mismatch_cls.name}_from_jsonable")
        )
        mismatch_property_name_literal = typescript_common.string_literal(
            mismatch_prop.json_name
        )

        blocks.append(
            Stripped(
                f"""\
test("{typescript_naming.class_name(mismatch_cls.name)} deserialization fails with property type mismatch", () => {{
{I}const jsonable = readExpectedJson(
{I}{I}{mismatch_cls_name_json_literal},
{I}{I}{typescript_common.string_literal(mismatch_file_name)}
{I});

{I}const jsonObject = {{ ...mustBeJsonObject(jsonable) }};
{I}jsonObject[{mismatch_property_name_literal}] = {{ definitely: "unexpected-object" }};

{I}const instanceOrError = OurJsonization.{mismatch_deserialization_function}(
{I}{I}jsonObject
{I});

{I}expect(instanceOrError.error).not.toBeNull();
}});"""
            )
        )

    if nested_dispatch_candidate is not None:
        nested_cls, nested_prop = nested_dispatch_candidate
        nested_cls_name_json_literal = typescript_common.string_literal(
            naming.json_model_type(nested_cls.name)
        )
        nested_deserialization_function = typescript_naming.function_name(
            Identifier(f"{nested_cls.name}_from_jsonable")
        )
        nested_property_name_literal = typescript_common.string_literal(
            nested_prop.json_name
        )
        model_type_property_name_literal = typescript_common.string_literal(
            naming.json_property(Identifier("model_type"))
        )

        blocks.append(
            Stripped(
                f"""\
test("{typescript_naming.class_name(nested_cls.name)} deserialization fails with invalid nested modelType", () => {{
{I}const jsonable = readExpectedJson(
{I}{I}{nested_cls_name_json_literal},
{I}{I}"maximal.json"
{I});

{I}const jsonObject = {{ ...mustBeJsonObject(jsonable) }};
{I}const nestedValue = jsonObject[{nested_property_name_literal}];

{I}if (
{I}{I}typeof nestedValue !== "object" ||
{I}{I}nestedValue === null ||
{I}{I}typeof nestedValue[Symbol.iterator] === "function"
{I}) {{
{I}{I}throw new Error("Expected nested class JSON object to be present in maximal example.");
{I}}}

{I}const nestedObject = {{ ...<OurJsonization.JsonObject>nestedValue }};
{I}nestedObject[{model_type_property_name_literal}] = "DefinitelyNotAModelType";
{I}jsonObject[{nested_property_name_literal}] = nestedObject;

{I}const instanceOrError = OurJsonization.{nested_deserialization_function}(
{I}{I}jsonObject
{I});

{I}expect(instanceOrError.error).not.toBeNull();
}});"""
            )
        )

    blocks.append(typescript_common.WARNING)

    writer = io.StringIO()
    for i, block in enumerate(blocks):
        if i > 0:
            writer.write("\n\n")

        writer.write(block)

    writer.write("\n")

    return writer.getvalue()


assert generate.__doc__ is not None
assert __doc__ is not None
assert generate.__doc__.strip().startswith(__doc__.strip())
