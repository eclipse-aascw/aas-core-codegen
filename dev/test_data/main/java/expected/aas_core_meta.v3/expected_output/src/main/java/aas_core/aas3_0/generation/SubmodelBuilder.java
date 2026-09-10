package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Submodel type.
 */
public class SubmodelBuilder {
  /**
   * An extension of the element.
   */
  private List<IExtension> extensions;

  /**
   * The category is a value that gives further meta information
   * w.r.t. to the class of the element.
   * It affects the expected existence of attributes and the applicability of
   * constraints.
   *
   * <p>The category is not identical to the semantic definition
   * ({@link aas_core.aas3_0.types.model.IHasSemantics}) of an element. The category e.g. could denote that
   * the element is a measurement value whereas the semantic definition of
   * the element would denote that it is the measured temperature.
   */
  private String category;

  /**
   * In case of identifiables this attribute is a short name of the element.
   * In case of referable this ID is an identifying string of the element within
   * its name space.
   *
   * <p>In case the element is a property and the property has a semantic definition
   * ({@link aas_core.aas3_0.types.model.IHasSemantics#getSemanticId()}) conformant to IEC61360
   * the {@link aas_core.aas3_0.types.model.IReferable#getIdShort()} is typically identical to the short name in English.
   */
  private String idShort;

  /**
   * Display name. Can be provided in several languages.
   */
  private List<ILangStringNameType> displayName;

  /**
   * Description or comments on the element.
   *
   * <p>The description can be provided in several languages.
   *
   * <p>If no description is defined, then the definition of the concept
   * description that defines the semantics of the element is used.
   *
   * <p>Additional information can be provided, e.g., if the element is
   * qualified and which qualifier types can be expected in which
   * context or which additional data specification templates are
   * provided.
   */
  private List<ILangStringTextType> description;

  /**
   * Administrative information of an identifiable element.
   *
   * <p>Some of the administrative information like the version number might need to
   * be part of the identification.
   */
  private IAdministrativeInformation administration;

  /**
   * The globally unique identification of the element.
   */
  private String id;

  /**
   * Kind of the element: either type or instance.
   *
   * <p>Default: {@link aas_core.aas3_0.types.enums.ModellingKind#INSTANCE}
   */
  private ModellingKind kind;

  /**
   * Identifier of the semantic definition of the element. It is called semantic ID
   * of the element or also main semantic ID of the element.
   *
   * <p>It is recommended to use a global reference.
   */
  private IReference semanticId;

  /**
   * Identifier of a supplemental semantic definition of the element.
   * It is called supplemental semantic ID of the element.
   *
   * <p>It is recommended to use a global reference.
   */
  private List<IReference> supplementalSemanticIds;

  /**
   * Additional qualification of a qualifiable element.
   *
   * <p>Constraints:
   *
   * <ul>
   *   <li> Constraint AASd-021:
   *   Every qualifiable can only have one qualifier with the same
   *   {@link aas_core.aas3_0.types.impl.Qualifier#getType()}.
   * </ul>
   */
  private List<IQualifier> qualifiers;

  /**
   * Embedded data specification.
   */
  private List<IEmbeddedDataSpecification> embeddedDataSpecifications;

  /**
   * A submodel consists of zero or more submodel elements.
   */
  private List<ISubmodelElement> submodelElements;

  public SubmodelBuilder(String id) {
    this.id = Objects.requireNonNull(
      id,
      "Argument \"id\" must be non-null.");
  }

  public SubmodelBuilder setExtensions(List<IExtension> extensions) {
    this.extensions = extensions;
    return this;
  }

  public SubmodelBuilder setCategory(String category) {
    this.category = category;
    return this;
  }

  public SubmodelBuilder setIdShort(String idShort) {
    this.idShort = idShort;
    return this;
  }

  public SubmodelBuilder setDisplayName(List<ILangStringNameType> displayName) {
    this.displayName = displayName;
    return this;
  }

  public SubmodelBuilder setDescription(List<ILangStringTextType> description) {
    this.description = description;
    return this;
  }

  public SubmodelBuilder setAdministration(IAdministrativeInformation administration) {
    this.administration = administration;
    return this;
  }

  public SubmodelBuilder setKind(ModellingKind kind) {
    this.kind = kind;
    return this;
  }

  public SubmodelBuilder setSemanticId(IReference semanticId) {
    this.semanticId = semanticId;
    return this;
  }

  public SubmodelBuilder setSupplementalSemanticIds(List<IReference> supplementalSemanticIds) {
    this.supplementalSemanticIds = supplementalSemanticIds;
    return this;
  }

  public SubmodelBuilder setQualifiers(List<IQualifier> qualifiers) {
    this.qualifiers = qualifiers;
    return this;
  }

  public SubmodelBuilder setEmbeddedDataSpecifications(List<IEmbeddedDataSpecification> embeddedDataSpecifications) {
    this.embeddedDataSpecifications = embeddedDataSpecifications;
    return this;
  }

  public SubmodelBuilder setSubmodelElements(List<ISubmodelElement> submodelElements) {
    this.submodelElements = submodelElements;
    return this;
  }

  public Submodel build() {
    return new Submodel(
      this.id,
      this.extensions,
      this.category,
      this.idShort,
      this.displayName,
      this.description,
      this.administration,
      this.kind,
      this.semanticId,
      this.supplementalSemanticIds,
      this.qualifiers,
      this.embeddedDataSpecifications,
      this.submodelElements);
  }
}
