package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Builder for the Something type.
 */
public class SomethingBuilder {
  private ObjectNode mapping;

  private ObjectNode optionalMapping;

  public SomethingBuilder(ObjectNode mapping) {
    this.mapping = Objects.requireNonNull(
      mapping,
      "Argument \"mapping\" must be non-null.");
  }

  public SomethingBuilder setOptionalMapping(ObjectNode optionalMapping) {
    this.optionalMapping = optionalMapping;
    return this;
  }

  public Something build() {
    return new Something(
      this.mapping,
      this.optionalMapping);
  }
}
