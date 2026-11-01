"""Generate the unit test code for Golang."""

from aas_core_codegen.golang.tests import (
    _generate_ourtesting_common_jsonization,
    _generate_ourtesting_constants,
    _generate_ourtesting_deep_equal,
    _generate_ourtesting_doc,
    _generate_ourtesting_filesystem,
    _generate_ourtesting_tracing,
    _generate_arithmetic_test,
    _generate_descend_test_common,
    _generate_descend_test_descend_once_test,
    _generate_descend_test_descend_test,
    _generate_enhancing_test,
    _generate_is_xxx_test,
    _generate_parse_int_test,
    _generate_safe_integer_test,
    _generate_string_helpers_test,
    _generate_jsonization_test_classes_with_descendants_test,
    _generate_jsonization_test_common_test,
    _generate_jsonization_test_concrete_classes_test,
    _generate_jsonization_test_enums_test,
    _generate_jsonization_test_json_value_test,
    _generate_verification_test,
    _generate_xmlization_test_concrete_classes_test,
    _generate_xmlization_test_common_test,
    _generate_xxx_or_default_test,
)

generate_ourtesting_common_jsonization = (
    _generate_ourtesting_common_jsonization.generate
)
generate_ourtesting_constants = _generate_ourtesting_constants.generate
generate_ourtesting_deep_equal = _generate_ourtesting_deep_equal.generate
generate_ourtesting_doc = _generate_ourtesting_doc.generate
generate_ourtesting_filesystem = _generate_ourtesting_filesystem.generate
generate_ourtesting_tracing = _generate_ourtesting_tracing.generate
generate_arithmetic_test = _generate_arithmetic_test.generate
generate_parse_int_test = _generate_parse_int_test.generate
generate_safe_integer_test = _generate_safe_integer_test.generate
generate_descend_test_common = _generate_descend_test_common.generate
generate_descend_test_descend_once_test = (
    _generate_descend_test_descend_once_test.generate
)
generate_descend_test_descend_test = _generate_descend_test_descend_test.generate
generate_enhancing_test = _generate_enhancing_test.generate
generate_is_xxx_test = _generate_is_xxx_test.generate
generate_string_helpers_test = _generate_string_helpers_test.generate
generate_jsonization_test_classes_with_descendants_test = (
    _generate_jsonization_test_classes_with_descendants_test.generate
)
generate_jsonization_test_common_test = _generate_jsonization_test_common_test.generate
generate_jsonization_test_concrete_classes_test = (
    _generate_jsonization_test_concrete_classes_test.generate
)
generate_jsonization_test_enums_test = _generate_jsonization_test_enums_test.generate
generate_jsonization_test_json_value_test = (
    _generate_jsonization_test_json_value_test.generate
)
generate_verification_test = _generate_verification_test.generate
generate_xmlization_test_concrete_classes_test = (
    _generate_xmlization_test_concrete_classes_test.generate
)
generate_xmlization_test_common_test = _generate_xmlization_test_common_test.generate
generate_xxx_or_default_test = _generate_xxx_or_default_test.generate
