package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the SpecificAssetId type.
 */
public class SpecificAssetIdBuilder {
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
   * Name of the identifier
   */
  private String name;

  /**
   * The value of the specific asset identifier with the corresponding name.
   */
  private String value;

  /**
   * The (external) subject the key belongs to or has meaning to.
   *
   * <p>This is a global reference.
   */
  private IReference externalSubjectId;

  public SpecificAssetIdBuilder(
    String name,
    String value) {
    this.name = Objects.requireNonNull(
      name,
      "Argument \"name\" must be non-null.");
    this.value = Objects.requireNonNull(
      value,
      "Argument \"value\" must be non-null.");
  }

  public SpecificAssetIdBuilder setSemanticId(IReference semanticId) {
    this.semanticId = semanticId;
    return this;
  }

  public SpecificAssetIdBuilder setSupplementalSemanticIds(List<IReference> supplementalSemanticIds) {
    this.supplementalSemanticIds = supplementalSemanticIds;
    return this;
  }

  public SpecificAssetIdBuilder setExternalSubjectId(IReference externalSubjectId) {
    this.externalSubjectId = externalSubjectId;
    return this;
  }

  public SpecificAssetId build() {
    return new SpecificAssetId(
      this.name,
      this.value,
      this.semanticId,
      this.supplementalSemanticIds,
      this.externalSubjectId);
  }
}
