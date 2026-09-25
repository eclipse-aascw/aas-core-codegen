"""Generate the unit test code for Golang."""

from aas_core_codegen.golang.tests import (
    _generate_aastesting_common_jsonization,
    _generate_aastesting_constants,
    _generate_aastesting_deep_equal,
    _generate_aastesting_doc,
    _generate_aastesting_filesystem,
    _generate_aastesting_tracing,
    _generate_descend_test_common,
    _generate_descend_test_descend_once_test,
    _generate_descend_test_descend_test,
    _generate_enhancing_test,
    _generate_is_xxx_test,
    _generate_string_helpers_test,
    _generate_jsonization_test_classes_with_descendants_test,
    _generate_jsonization_test_common_test,
    _generate_jsonization_test_concrete_classes_test,
    _generate_jsonization_test_enums_test,
    _generate_verification_test,
    _generate_xmlization_test_concrete_classes_test,
    _generate_xmlization_test_common_test,
    _generate_xxx_or_default_test,
)

generate_aastesting_common_jsonization = (
    _generate_aastesting_common_jsonization.generate
)
generate_aastesting_constants = _generate_aastesting_constants.generate
generate_aastesting_deep_equal = _generate_aastesting_deep_equal.generate
generate_aastesting_doc = _generate_aastesting_doc.generate
generate_aastesting_filesystem = _generate_aastesting_filesystem.generate
generate_aastesting_tracing = _generate_aastesting_tracing.generate
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
generate_verification_test = _generate_verification_test.generate
generate_xmlization_test_concrete_classes_test = (
    _generate_xmlization_test_concrete_classes_test.generate
)
generate_xmlization_test_common_test = _generate_xmlization_test_common_test.generate
generate_xxx_or_default_test = _generate_xxx_or_default_test.generate
