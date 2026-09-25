"""Generate the unit test code for C#."""

from aas_core_codegen.csharp.tests import (
    _generate_common,
    _generate_common_json,
    _generate_common_jsonization,
    _generate_test_copying,
    _generate_test_descend_and_visitor_through,
    _generate_test_descend_once,
    _generate_test_enhancing,
    _generate_test_jsonization_of_concrete_classes,
    _generate_test_jsonization_of_enums,
    _generate_test_jsonization_of_interfaces,
    _generate_test_over_x_or_empty,
    _generate_test_string_helpers,
    _generate_test_verification_of_enums,
    _generate_test_x_or_default,
    _generate_test_xml_rpc,
    _generate_test_xmlization_errors,
    _generate_test_xmlization_of_concrete_classes,
    _generate_test_xmlization_of_interfaces,
)

generate_common = _generate_common.generate
generate_common_json = _generate_common_json.generate
generate_common_jsonization = _generate_common_jsonization.generate
generate_test_copying = _generate_test_copying.generate
generate_test_descend_and_visitor_through = (
    _generate_test_descend_and_visitor_through.generate
)
generate_test_descend_once = _generate_test_descend_once.generate
generate_test_enhancing = _generate_test_enhancing.generate
generate_test_jsonization_of_concrete_classes = (
    _generate_test_jsonization_of_concrete_classes.generate
)
generate_test_jsonization_of_enums = _generate_test_jsonization_of_enums.generate
generate_test_jsonization_of_interfaces = (
    _generate_test_jsonization_of_interfaces.generate
)
generate_test_over_x_or_empty = _generate_test_over_x_or_empty.generate
generate_test_string_helpers = _generate_test_string_helpers.generate
generate_test_verification_of_enums = _generate_test_verification_of_enums.generate
generate_test_x_or_default = _generate_test_x_or_default.generate
generate_test_xml_rpc = _generate_test_xml_rpc.generate
generate_test_xmlization_errors = _generate_test_xmlization_errors.generate
generate_test_xmlization_of_concrete_classes = (
    _generate_test_xmlization_of_concrete_classes.generate
)
generate_test_xmlization_of_interfaces = (
    _generate_test_xmlization_of_interfaces.generate
)
