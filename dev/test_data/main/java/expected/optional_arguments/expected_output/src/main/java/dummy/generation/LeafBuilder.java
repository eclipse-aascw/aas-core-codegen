package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Leaf type.
 */
public class LeafBuilder {
  private IItem optionalItem;

  public LeafBuilder setOptionalItem(IItem optionalItem) {
    this.optionalItem = optionalItem;
    return this;
  }

  public Leaf build() {
    return new Leaf(this.optionalItem);
  }
}
