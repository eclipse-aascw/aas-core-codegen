package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the AssetInformation type.
 */
public class AssetInformationBuilder {
  /**
   * Denotes whether the Asset is of kind {@link aas_core.aas3_0.types.enums.AssetKind#TYPE} or
   * {@link aas_core.aas3_0.types.enums.AssetKind#INSTANCE}.
   */
  private AssetKind assetKind;

  /**
   * Global identifier of the asset the AAS is representing.
   *
   * <p>This attribute is required as soon as the AAS is exchanged via partners in the life
   * cycle of the asset. In a first phase of the life cycle the asset might not yet have
   * a global ID but already an internal identifier. The internal identifier would be
   * modelled via {@link aas_core.aas3_0.types.impl.AssetInformation#getSpecificAssetIds()}.
   *
   * <p>This is a global reference.
   */
  private String globalAssetId;

  /**
   * Additional domain-specific, typically proprietary identifier for the asset like
   * e.g., serial number etc.
   */
  private List<ISpecificAssetId> specificAssetIds;

  /**
   * In case {@link aas_core.aas3_0.types.impl.AssetInformation#getAssetKind()} is applicable the {@link aas_core.aas3_0.types.impl.AssetInformation#getAssetType()} is the asset ID
   * of the type asset of the asset under consideration
   * as identified by {@link aas_core.aas3_0.types.impl.AssetInformation#getGlobalAssetId()}.
   *
   * <p>In case {@link aas_core.aas3_0.types.impl.AssetInformation#getAssetKind()} is "Instance" than the {@link aas_core.aas3_0.types.impl.AssetInformation#getAssetType()} denotes
   * which "Type" the asset is of. But it is also possible
   * to have an {@link aas_core.aas3_0.types.impl.AssetInformation#getAssetType()} of an asset of kind "Type".
   */
  private String assetType;

  /**
   * Thumbnail of the asset represented by the Asset Administration Shell.
   *
   * <p>Used as default.
   */
  private IResource defaultThumbnail;

  public AssetInformationBuilder(AssetKind assetKind) {
    this.assetKind = Objects.requireNonNull(
      assetKind,
      "Argument \"assetKind\" must be non-null.");
  }

  public AssetInformationBuilder setGlobalAssetId(String globalAssetId) {
    this.globalAssetId = globalAssetId;
    return this;
  }

  public AssetInformationBuilder setSpecificAssetIds(List<ISpecificAssetId> specificAssetIds) {
    this.specificAssetIds = specificAssetIds;
    return this;
  }

  public AssetInformationBuilder setAssetType(String assetType) {
    this.assetType = assetType;
    return this;
  }

  public AssetInformationBuilder setDefaultThumbnail(IResource defaultThumbnail) {
    this.defaultThumbnail = defaultThumbnail;
    return this;
  }

  public AssetInformation build() {
    return new AssetInformation(
      this.assetKind,
      this.globalAssetId,
      this.specificAssetIds,
      this.assetType,
      this.defaultThumbnail);
  }
}
