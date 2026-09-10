package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the AssetAdministrationShell type.
 */
public class AssetAdministrationShellBuilder {
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
   * Embedded data specification.
   */
  private List<IEmbeddedDataSpecification> embeddedDataSpecifications;

  /**
   * The reference to the AAS the AAS was derived from.
   */
  private IReference derivedFrom;

  /**
   * Meta-information about the asset the AAS is representing.
   */
  private IAssetInformation assetInformation;

  /**
   * References to submodels of the AAS.
   *
   * <p>A submodel is a description of an aspect of the asset the AAS is representing.
   *
   * <p>The asset of an AAS is typically described by one or more submodels.
   *
   * <p>Temporarily no submodel might be assigned to the AAS.
   */
  private List<IReference> submodels;

  public AssetAdministrationShellBuilder(
    String id,
    IAssetInformation assetInformation) {
    this.id = Objects.requireNonNull(
      id,
      "Argument \"id\" must be non-null.");
    this.assetInformation = Objects.requireNonNull(
      assetInformation,
      "Argument \"assetInformation\" must be non-null.");
  }

  public AssetAdministrationShellBuilder setExtensions(List<IExtension> extensions) {
    this.extensions = extensions;
    return this;
  }

  public AssetAdministrationShellBuilder setCategory(String category) {
    this.category = category;
    return this;
  }

  public AssetAdministrationShellBuilder setIdShort(String idShort) {
    this.idShort = idShort;
    return this;
  }

  public AssetAdministrationShellBuilder setDisplayName(List<ILangStringNameType> displayName) {
    this.displayName = displayName;
    return this;
  }

  public AssetAdministrationShellBuilder setDescription(List<ILangStringTextType> description) {
    this.description = description;
    return this;
  }

  public AssetAdministrationShellBuilder setAdministration(IAdministrativeInformation administration) {
    this.administration = administration;
    return this;
  }

  public AssetAdministrationShellBuilder setEmbeddedDataSpecifications(List<IEmbeddedDataSpecification> embeddedDataSpecifications) {
    this.embeddedDataSpecifications = embeddedDataSpecifications;
    return this;
  }

  public AssetAdministrationShellBuilder setDerivedFrom(IReference derivedFrom) {
    this.derivedFrom = derivedFrom;
    return this;
  }

  public AssetAdministrationShellBuilder setSubmodels(List<IReference> submodels) {
    this.submodels = submodels;
    return this;
  }

  public AssetAdministrationShell build() {
    return new AssetAdministrationShell(
      this.id,
      this.assetInformation,
      this.extensions,
      this.category,
      this.idShort,
      this.displayName,
      this.description,
      this.administration,
      this.embeddedDataSpecifications,
      this.derivedFrom,
      this.submodels);
  }
}
