"""Provide generators for the main module."""

from aas_core_codegen.python.lib import (
    _generate_common,
    _generate_constants,
    _generate_json_value_verification,
    _generate_jsonization,
    _generate_reporting,
    _generate_stringification,
    _generate_types,
    _generate_verification,
    _generate_xml_common,
    _generate_xml_rpc,
    _generate_xmlization,
)

generate_common = _generate_common.generate

generate_constants = _generate_constants.generate

generate_json_value_verification = _generate_json_value_verification.generate

generate_jsonization = _generate_jsonization.generate

generate_reporting = _generate_reporting.generate

generate_stringification = _generate_stringification.generate

generate_types = _generate_types.generate
verify_for_types = _generate_types.verify

generate_verification = _generate_verification.generate
verify_for_verification = _generate_verification.verify

generate_xml_common = _generate_xml_common.generate

generate_xml_rpc = _generate_xml_rpc.generate

generate_xmlization = _generate_xmlization.generate
