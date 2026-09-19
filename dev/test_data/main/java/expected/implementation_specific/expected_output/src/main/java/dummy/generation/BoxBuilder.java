package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Box type.
 */
public class BoxBuilder {
  private String label;

  private Color color;

  public BoxBuilder(String label) {
    this.label = Objects.requireNonNull(
      label,
      "Argument \"label\" must be non-null.");
  }

  public BoxBuilder setColor(Color color) {
    this.color = color;
    return this;
  }

  public Box build() {
    return new Box(
      this.label,
      this.color);
  }
}
