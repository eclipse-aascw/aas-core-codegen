"""Provide generators for the main package."""

from aas_core_codegen.typescript.lib import (
    _generate_common,
    _generate_constants,
    _generate_index,
    _generate_jsonization,
    _generate_xmlization,
    _generate_stringification,
    _generate_types,
    _generate_verification,
    _generate_xml_common,
    _generate_xml_rpc,
)

generate_common = _generate_common.generate

generate_constants = _generate_constants.generate

generate_index = _generate_index.generate

generate_jsonization = _generate_jsonization.generate

generate_xmlization = _generate_xmlization.generate

generate_stringification = _generate_stringification.generate

generate_types = _generate_types.generate
verify_for_types = _generate_types.verify

generate_verification = _generate_verification.generate
verify_verification_functions = _generate_verification.verify

generate_xml_common = _generate_xml_common.generate

generate_xml_rpc = _generate_xml_rpc.generate
