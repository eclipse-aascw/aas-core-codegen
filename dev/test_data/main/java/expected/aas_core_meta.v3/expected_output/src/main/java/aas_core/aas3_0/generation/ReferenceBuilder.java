package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Reference type.
 */
public class ReferenceBuilder {
  /**
   * Type of the reference.
   *
   * <p>Denotes, whether reference is an external reference or a model reference.
   */
  private ReferenceTypes type;

  /**
   * {@link aas_core.aas3_0.types.model.IHasSemantics#getSemanticId()} of the referenced model element
   * ({@link aas_core.aas3_0.types.impl.Reference#getType()} = {@link aas_core.aas3_0.types.enums.ReferenceTypes#MODEL_REFERENCE}).
   *
   * <p>For external references there typically is no semantic ID.
   *
   * <p>It is recommended to use a external reference.
   */
  private IReference referredSemanticId;

  /**
   * Unique references in their name space.
   */
  private List<IKey> keys;

  public ReferenceBuilder(
    ReferenceTypes type,
    List<IKey> keys) {
    this.type = Objects.requireNonNull(
      type,
      "Argument \"type\" must be non-null.");
    this.keys = Objects.requireNonNull(
      keys,
      "Argument \"keys\" must be non-null.");
  }

  public ReferenceBuilder setReferredSemanticId(IReference referredSemanticId) {
    this.referredSemanticId = referredSemanticId;
    return this;
  }

  public Reference build() {
    return new Reference(
      this.type,
      this.keys,
      this.referredSemanticId);
  }
}
