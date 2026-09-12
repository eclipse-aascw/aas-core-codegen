"""Generate the unit test code for C++."""

from aas_core_codegen.cpp.tests import (
    _generate_common,
    _generate_common_examples,
    _generate_common_jsonization,
    _generate_common_xmlization,
    _generate_test_descent_and_descent_once,
    _generate_test_jsonization_dispatch,
    _generate_test_jsonization_of_concrete_classes,
    _generate_test_revm,
    _generate_test_stringification_base64,
    _generate_test_stringification_of_enums,
    _generate_test_verification,
    _generate_test_wstringification_of_enums,
    _generate_test_xml_rpc,
    _generate_test_xmlization_dispatch,
    _generate_test_xmlization_of_concrete_classes,
    _generate_test_x_or_default,
)

generate_common_header = _generate_common.generate_header
generate_common_implementation = _generate_common.generate_implementation

generate_common_examples_header = _generate_common_examples.generate_header
generate_common_examples_implementation = (
    _generate_common_examples.generate_implementation
)

generate_common_jsonization_header = _generate_common_jsonization.generate_header
generate_common_jsonization_implementation = (
    _generate_common_jsonization.generate_implementation
)

generate_common_xmlization_header = _generate_common_xmlization.generate_header
generate_common_xmlization_implementation = (
    _generate_common_xmlization.generate_implementation
)

generate_test_descent_and_descent_once_implementation = (
    _generate_test_descent_and_descent_once.generate_implementation
)
generate_test_jsonization_dispatch_implementation = (
    _generate_test_jsonization_dispatch.generate_implementation
)
generate_test_jsonization_of_concrete_classes_implementation = (
    _generate_test_jsonization_of_concrete_classes.generate_implementation
)
generate_test_revm_implementation = _generate_test_revm.generate_implementation
generate_test_stringification_base64_implementation = (
    _generate_test_stringification_base64.generate_implementation
)
generate_test_stringification_of_enums_implementation = (
    _generate_test_stringification_of_enums.generate_implementation
)
generate_test_verification_implementation = (
    _generate_test_verification.generate_implementation
)
generate_test_wstringification_of_enums_implementation = (
    _generate_test_wstringification_of_enums.generate_implementation
)
generate_test_xml_rpc_implementation = _generate_test_xml_rpc.generate_implementation
generate_test_xmlization_dispatch_implementation = (
    _generate_test_xmlization_dispatch.generate_implementation
)
generate_test_xmlization_of_concrete_classes_implementation = (
    _generate_test_xmlization_of_concrete_classes.generate_implementation
)
generate_test_x_or_default_implementation = (
    _generate_test_x_or_default.generate_implementation
)
