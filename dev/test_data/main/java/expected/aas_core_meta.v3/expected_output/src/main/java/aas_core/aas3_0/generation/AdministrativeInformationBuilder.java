package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the AdministrativeInformation type.
 */
public class AdministrativeInformationBuilder {
  /**
   * Embedded data specification.
   */
  private List<IEmbeddedDataSpecification> embeddedDataSpecifications;

  /**
   * Version of the element.
   */
  private String version;

  /**
   * Revision of the element.
   */
  private String revision;

  /**
   * The subject ID of the subject responsible for making the element.
   */
  private IReference creator;

  /**
   * Identifier of the template that guided the creation of the element.
   *
   * <p>In case of a submodel the {@link aas_core.aas3_0.types.impl.AdministrativeInformation#getTemplateId()} is the identifier
   * of the submodel template ID that guided the creation of the submodel
   *
   * <p>The {@link aas_core.aas3_0.types.impl.AdministrativeInformation#getTemplateId()} is not relevant for validation in Submodels.
   * For validation the {@link aas_core.aas3_0.types.impl.Submodel#getSemanticId()} shall be used.
   *
   * <p>Usage of {@link aas_core.aas3_0.types.impl.AdministrativeInformation#getTemplateId()} is not restricted to submodel instances. So also
   * the creation of submodel templates can be guided by another submodel template.
   */
  private String templateId;

  public AdministrativeInformationBuilder setEmbeddedDataSpecifications(List<IEmbeddedDataSpecification> embeddedDataSpecifications) {
    this.embeddedDataSpecifications = embeddedDataSpecifications;
    return this;
  }

  public AdministrativeInformationBuilder setVersion(String version) {
    this.version = version;
    return this;
  }

  public AdministrativeInformationBuilder setRevision(String revision) {
    this.revision = revision;
    return this;
  }

  public AdministrativeInformationBuilder setCreator(IReference creator) {
    this.creator = creator;
    return this;
  }

  public AdministrativeInformationBuilder setTemplateId(String templateId) {
    this.templateId = templateId;
    return this;
  }

  public AdministrativeInformation build() {
    return new AdministrativeInformation(
      this.embeddedDataSpecifications,
      this.version,
      this.revision,
      this.creator,
      this.templateId);
  }
}
