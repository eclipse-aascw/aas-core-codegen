package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Something type.
 */
public class SomethingBuilder {
  private StructuralUnion structuralProperty;

  private MixedUnion mixedProperty;

  private ModelTypedUnion modelTypedProperty;

  private List<StructuralUnion> listStructuralProperty;

  private List<MixedUnion> listMixedProperty;

  private List<ModelTypedUnion> listModelTypedProperty;

  private Tuple3<StructuralUnion, MixedUnion, ModelTypedUnion> tupleProperty;

  private StructuralUnion optionalStructuralProperty;

  private MixedUnion optionalMixedProperty;

  private ModelTypedUnion optionalModelTypedProperty;

  public SomethingBuilder(
    StructuralUnion structuralProperty,
    MixedUnion mixedProperty,
    ModelTypedUnion modelTypedProperty,
    List<StructuralUnion> listStructuralProperty,
    List<MixedUnion> listMixedProperty,
    List<ModelTypedUnion> listModelTypedProperty,
    Tuple3<StructuralUnion, MixedUnion, ModelTypedUnion> tupleProperty) {
    this.structuralProperty = Objects.requireNonNull(
      structuralProperty,
      "Argument \"structuralProperty\" must be non-null.");
    this.mixedProperty = Objects.requireNonNull(
      mixedProperty,
      "Argument \"mixedProperty\" must be non-null.");
    this.modelTypedProperty = Objects.requireNonNull(
      modelTypedProperty,
      "Argument \"modelTypedProperty\" must be non-null.");
    this.listStructuralProperty = Objects.requireNonNull(
      listStructuralProperty,
      "Argument \"listStructuralProperty\" must be non-null.");
    this.listMixedProperty = Objects.requireNonNull(
      listMixedProperty,
      "Argument \"listMixedProperty\" must be non-null.");
    this.listModelTypedProperty = Objects.requireNonNull(
      listModelTypedProperty,
      "Argument \"listModelTypedProperty\" must be non-null.");
    this.tupleProperty = Objects.requireNonNull(
      tupleProperty,
      "Argument \"tupleProperty\" must be non-null.");
  }

  public SomethingBuilder setOptionalStructuralProperty(StructuralUnion optionalStructuralProperty) {
    this.optionalStructuralProperty = optionalStructuralProperty;
    return this;
  }

  public SomethingBuilder setOptionalMixedProperty(MixedUnion optionalMixedProperty) {
    this.optionalMixedProperty = optionalMixedProperty;
    return this;
  }

  public SomethingBuilder setOptionalModelTypedProperty(ModelTypedUnion optionalModelTypedProperty) {
    this.optionalModelTypedProperty = optionalModelTypedProperty;
    return this;
  }

  public Something build() {
    return new Something(
      this.structuralProperty,
      this.mixedProperty,
      this.modelTypedProperty,
      this.listStructuralProperty,
      this.listMixedProperty,
      this.listModelTypedProperty,
      this.tupleProperty,
      this.optionalStructuralProperty,
      this.optionalMixedProperty,
      this.optionalModelTypedProperty);
  }
}
