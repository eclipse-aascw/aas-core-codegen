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
  private Tuple2<String, Long> pair;

  private Tuple2<IAbstractItem, IAbstractItem> items;

  private Tuple6<
    Long,
    ISomeItem,
    IAbstractItem,
    ISomeItem,
    Long,
    Result> tricky;

  private Tuple2<String, IAbstractItem> optionalPair;

  public SomethingBuilder(
    Tuple2<String, Long> pair,
    Tuple2<IAbstractItem, IAbstractItem> items,
    Tuple6<
      Long,
      ISomeItem,
      IAbstractItem,
      ISomeItem,
      Long,
      Result> tricky) {
    this.pair = Objects.requireNonNull(
      pair,
      "Argument \"pair\" must be non-null.");
    this.items = Objects.requireNonNull(
      items,
      "Argument \"items\" must be non-null.");
    this.tricky = Objects.requireNonNull(
      tricky,
      "Argument \"tricky\" must be non-null.");
  }

  public SomethingBuilder setOptionalPair(Tuple2<String, IAbstractItem> optionalPair) {
    this.optionalPair = optionalPair;
    return this;
  }

  public Something build() {
    return new Something(
      this.pair,
      this.items,
      this.tricky,
      this.optionalPair);
  }
}
