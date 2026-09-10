package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Environment type.
 */
public class EnvironmentBuilder {
  /**
   * Asset administration shell
   */
  private List<IAssetAdministrationShell> assetAdministrationShells;

  /**
   * Submodel
   */
  private List<ISubmodel> submodels;

  /**
   * Concept description
   */
  private List<IConceptDescription> conceptDescriptions;

  public EnvironmentBuilder setAssetAdministrationShells(List<IAssetAdministrationShell> assetAdministrationShells) {
    this.assetAdministrationShells = assetAdministrationShells;
    return this;
  }

  public EnvironmentBuilder setSubmodels(List<ISubmodel> submodels) {
    this.submodels = submodels;
    return this;
  }

  public EnvironmentBuilder setConceptDescriptions(List<IConceptDescription> conceptDescriptions) {
    this.conceptDescriptions = conceptDescriptions;
    return this;
  }

  public Environment build() {
    return new Environment(
      this.assetAdministrationShells,
      this.submodels,
      this.conceptDescriptions);
  }
}
