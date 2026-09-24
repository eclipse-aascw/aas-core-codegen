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
  private IElement root;

  private IElement optionalElement;

  private Value value;

  private List<Value> values;

  public SomethingBuilder(
    IElement root,
    Value value,
    List<Value> values) {
    this.root = Objects.requireNonNull(
      root,
      "Argument \"root\" must be non-null.");
    this.value = Objects.requireNonNull(
      value,
      "Argument \"value\" must be non-null.");
    this.values = Objects.requireNonNull(
      values,
      "Argument \"values\" must be non-null.");
  }

  public SomethingBuilder setOptionalElement(IElement optionalElement) {
    this.optionalElement = optionalElement;
    return this;
  }

  public Something build() {
    return new Something(
      this.root,
      this.value,
      this.values,
      this.optionalElement);
  }
}
