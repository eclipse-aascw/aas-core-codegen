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
  private Double someFloat;

  private Double someOptionalFloat;

  private List<Double> someFloats;

  private Tuple2<String, Double> somePair;

  public SomethingBuilder(
    Double someFloat,
    List<Double> someFloats,
    Tuple2<String, Double> somePair) {
    this.someFloat = Objects.requireNonNull(
      someFloat,
      "Argument \"someFloat\" must be non-null.");
    this.someFloats = Objects.requireNonNull(
      someFloats,
      "Argument \"someFloats\" must be non-null.");
    this.somePair = Objects.requireNonNull(
      somePair,
      "Argument \"somePair\" must be non-null.");
  }

  public SomethingBuilder setSomeOptionalFloat(Double someOptionalFloat) {
    this.someOptionalFloat = someOptionalFloat;
    return this;
  }

  public Something build() {
    return new Something(
      this.someFloat,
      this.someFloats,
      this.somePair,
      this.someOptionalFloat);
  }
}
