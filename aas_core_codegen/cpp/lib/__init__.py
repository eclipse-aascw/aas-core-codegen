"""Provide generators for the main library."""

from aas_core_codegen.cpp.lib import (
    _generate_common,
    _generate_constants,
    _generate_enhancing,
    _generate_iteration,
    _generate_json_value_verification,
    _generate_jsonization,
    _generate_pattern,
    _generate_revm,
    _generate_stringification,
    _generate_types,
    _generate_verification,
    _generate_visitation,
    _generate_wstringification,
    _generate_xml_common,
    _generate_xml_rpc,
    _generate_xmlization,
)

generate_common_header = _generate_common.generate_header
generate_common_implementation = _generate_common.generate_implementation

generate_constants_header = _generate_constants.generate_header
generate_constants_implementation = _generate_constants.generate_implementation

generate_enhancing_header = _generate_enhancing.generate_header

generate_iteration_header = _generate_iteration.generate_header
generate_iteration_implementation = _generate_iteration.generate_implementation

generate_json_value_verification_header = (
    _generate_json_value_verification.generate_header
)
generate_json_value_verification_implementation = (
    _generate_json_value_verification.generate_implementation
)

generate_jsonization_header = _generate_jsonization.generate_header
generate_jsonization_implementation = _generate_jsonization.generate_implementation

generate_pattern_header = _generate_pattern.generate_header
generate_pattern_implementation = _generate_pattern.generate_implementation

generate_revm_header = _generate_revm.generate_header
generate_revm_implementation = _generate_revm.generate_implementation

generate_stringification_header = _generate_stringification.generate_header
generate_stringification_implementation = (
    _generate_stringification.generate_implementation
)

generate_types_header = _generate_types.generate_header
generate_types_implementation = _generate_types.generate_implementation

generate_verification_header = _generate_verification.generate_header
generate_verification_implementation = _generate_verification.generate_implementation

generate_visitation_header = _generate_visitation.generate_header
generate_visitation_implementation = _generate_visitation.generate_implementation

generate_wstringification_header = _generate_wstringification.generate_header
generate_wstringification_implementation = (
    _generate_wstringification.generate_implementation
)

generate_xml_common_header = _generate_xml_common.generate_header
generate_xml_common_implementation = _generate_xml_common.generate_implementation

generate_xml_rpc_header = _generate_xml_rpc.generate_header
generate_xml_rpc_implementation = _generate_xml_rpc.generate_implementation

generate_xmlization_header = _generate_xmlization.generate_header
generate_xmlization_implementation = _generate_xmlization.generate_implementation

verify_for_types = _generate_types.verify
