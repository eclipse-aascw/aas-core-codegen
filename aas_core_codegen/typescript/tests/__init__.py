"""Generate the unit test code for TypeScript."""

from aas_core_codegen.typescript.tests import (
    _generate_common,
    _generate_common_base64_spec,
    _generate_common_base64url_spec,
    _generate_common_string_helpers_spec,
    _generate_common_jsonization,
    _generate_common_xmlization,
    _generate_jsonization_common_spec,
    _generate_jsonization_concrete_classes_spec,
    _generate_jsonization_enums_spec,
    _generate_jsonization_interfaces_spec,
    _generate_jsonization_negative_spec,
    _generate_stringification_enums_spec,
    _generate_xmlization_concrete_classes_spec,
    _generate_xmlization_basic_spec,
    _generate_xmlization_common_spec,
    _generate_xmlization_enums_spec,
    _generate_xmlization_interfaces_spec,
    _generate_xmlization_negative_spec,
    _generate_types_casts_spec,
    _generate_types_descend_and_pass_through_visitor_spec,
    _generate_types_descend_once_spec,
    _generate_types_model_type_spec,
    _generate_types_over_enum_spec,
    _generate_types_over_x_or_empty_spec,
    _generate_types_type_matches_spec,
    _generate_types_x_or_default_spec,
    _generate_verification_json_value_spec,
    _generate_verification_spec,
    _generate_xml_rpc_spec,
)

generate_common = _generate_common.generate
generate_common_base64_spec = _generate_common_base64_spec.generate
generate_common_base64url_spec = _generate_common_base64url_spec.generate
generate_common_string_helpers_spec = _generate_common_string_helpers_spec.generate
generate_common_jsonization = _generate_common_jsonization.generate
generate_common_xmlization = _generate_common_xmlization.generate
generate_jsonization_common_spec = _generate_jsonization_common_spec.generate
generate_jsonization_concrete_classes_spec = (
    _generate_jsonization_concrete_classes_spec.generate
)
generate_jsonization_enums_spec = _generate_jsonization_enums_spec.generate
generate_jsonization_interfaces_spec = _generate_jsonization_interfaces_spec.generate
generate_jsonization_negative_spec = _generate_jsonization_negative_spec.generate
generate_stringification_enums_spec = _generate_stringification_enums_spec.generate
generate_xmlization_concrete_classes_spec = (
    _generate_xmlization_concrete_classes_spec.generate
)
generate_xmlization_basic_spec = _generate_xmlization_basic_spec.generate
generate_xmlization_common_spec = _generate_xmlization_common_spec.generate
generate_xmlization_enums_spec = _generate_xmlization_enums_spec.generate
generate_xmlization_interfaces_spec = _generate_xmlization_interfaces_spec.generate
generate_xmlization_negative_spec = _generate_xmlization_negative_spec.generate
generate_types_casts_spec = _generate_types_casts_spec.generate
generate_types_descend_and_pass_through_visitor_spec = (
    _generate_types_descend_and_pass_through_visitor_spec.generate
)
generate_types_descend_once_spec = _generate_types_descend_once_spec.generate
generate_types_model_type_spec = _generate_types_model_type_spec.generate
generate_types_over_enum_spec = _generate_types_over_enum_spec.generate
generate_types_over_x_or_empty_spec = _generate_types_over_x_or_empty_spec.generate
generate_types_type_matches_spec = _generate_types_type_matches_spec.generate
generate_types_x_or_default_spec = _generate_types_x_or_default_spec.generate
generate_verification_spec = _generate_verification_spec.generate

generate_verification_json_value_spec = _generate_verification_json_value_spec.generate

generate_xml_rpc_spec = _generate_xml_rpc_spec.generate
