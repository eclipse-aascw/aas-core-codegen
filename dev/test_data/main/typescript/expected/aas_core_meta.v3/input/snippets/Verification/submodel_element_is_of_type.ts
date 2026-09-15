// NOTE (mristin):
// The literals of AasTypes.AasSubmodelElements are consecutive integers starting
// at 0, so we index into an array instead of looking the check up in a map.
const AAS_SUBMODEL_ELEMENTS_TO_IS: ReadonlyArray<
  (that: AasTypes.Class) => boolean
> = [
  AasTypes.isAnnotatedRelationshipElement,
  AasTypes.isBasicEventElement,
  AasTypes.isBlob,
  AasTypes.isCapability,
  AasTypes.isDataElement,
  AasTypes.isEntity,
  AasTypes.isEventElement,
  AasTypes.isFile,
  AasTypes.isMultiLanguageProperty,
  AasTypes.isOperation,
  AasTypes.isProperty,
  AasTypes.isRange,
  AasTypes.isReferenceElement,
  AasTypes.isRelationshipElement,
  AasTypes.isSubmodelElement,
  AasTypes.isSubmodelElementList,
  AasTypes.isSubmodelElementCollection
];

function assertAllTypesCoveredInAasSubmodelElementsToIs() {
  for (const literal of AasTypes.overAasSubmodelElements()) {
    if (AAS_SUBMODEL_ELEMENTS_TO_IS[literal] === undefined) {
      throw new Error(
        `The enumeration literal ${literal} of AasTypes.AasSubmodelElements ` +
          "is not covered in AAS_SUBMODEL_ELEMENTS_TO_IS"
      );
    }
  }
}
assertAllTypesCoveredInAasSubmodelElementsToIs();

/**
 * Check that `element` is an instance of class corresponding to
 * `expectedType`.
 *
 * @param element - to be checked for type
 * @param expectedType - in the check
 * @returns `true` if `element` corresponds to `expectedType`
 */
export function submodelElementIsOfType(
  element: AasTypes.ISubmodelElement,
  expectedType: AasTypes.AasSubmodelElements
): boolean {
  const isFunc = AAS_SUBMODEL_ELEMENTS_TO_IS[expectedType];
  return isFunc(element);
}
