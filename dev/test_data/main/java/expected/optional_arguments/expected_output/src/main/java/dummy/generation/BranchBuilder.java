package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Branch type.
 */
public class BranchBuilder {
  private List<INode> optionalChildren;

  public BranchBuilder setOptionalChildren(List<INode> optionalChildren) {
    this.optionalChildren = optionalChildren;
    return this;
  }

  public Branch build() {
    return new Branch(this.optionalChildren);
  }
}
