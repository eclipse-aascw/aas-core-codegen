"""Generate the unit test code for Python."""

from aas_core_codegen.python.tests import (
    _generate_common,
    _generate_common_jsonization,
    _generate_common_xmlization,
    _generate_test_descend_and_pass_through_visitor,
    _generate_test_descend_once,
    _generate_test_json_value_verification,
    _generate_test_len_slicing_and_find,
    _generate_test_jsonization_of_classes_with_descendants,
    _generate_test_jsonization_of_concrete_classes,
    _generate_test_jsonization_of_enums,
    _generate_test_for_over_x_or_empty,
    _generate_test_for_x_or_default,
    _generate_test_verification,
    _generate_test_xml_rpc,
    _generate_test_xmlization_of_classes_with_descendants,
    _generate_test_xmlization_of_concrete_classes,
)

generate_common = _generate_common.generate
generate_common_jsonization = _generate_common_jsonization.generate
generate_common_xmlization = _generate_common_xmlization.generate
generate_test_descend_and_pass_through_visitor = (
    _generate_test_descend_and_pass_through_visitor.generate
)
generate_test_descend_once = _generate_test_descend_once.generate
generate_test_json_value_verification = _generate_test_json_value_verification.generate
generate_test_len_slicing_and_find = _generate_test_len_slicing_and_find.generate
generate_test_jsonization_of_classes_with_descendants = (
    _generate_test_jsonization_of_classes_with_descendants.generate
)
generate_test_jsonization_of_concrete_classes = (
    _generate_test_jsonization_of_concrete_classes.generate
)
generate_test_jsonization_of_enums = _generate_test_jsonization_of_enums.generate
generate_test_for_over_x_or_empty = _generate_test_for_over_x_or_empty.generate
generate_test_for_x_or_default = _generate_test_for_x_or_default.generate
generate_test_verification = _generate_test_verification.generate
generate_test_xml_rpc = _generate_test_xml_rpc.generate
generate_test_xmlization_of_classes_with_descendants = (
    _generate_test_xmlization_of_classes_with_descendants.generate
)
generate_test_xmlization_of_concrete_classes = (
    _generate_test_xmlization_of_concrete_classes.generate
)
