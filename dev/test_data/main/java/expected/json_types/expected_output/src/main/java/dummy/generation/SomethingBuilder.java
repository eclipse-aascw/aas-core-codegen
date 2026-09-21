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
  private JsonNode value;

  private ArrayNode values;

  private ObjectNode mapping;

  private ObjectNode mappingWithConstrainedKey;

  private JsonNode optionalValue;

  private ArrayNode optionalValues;

  private ObjectNode optionalMapping;

  public SomethingBuilder(
    JsonNode value,
    ArrayNode values,
    ObjectNode mapping,
    ObjectNode mappingWithConstrainedKey) {
    this.value = Objects.requireNonNull(
      value,
      "Argument \"value\" must be non-null.");
    this.values = Objects.requireNonNull(
      values,
      "Argument \"values\" must be non-null.");
    this.mapping = Objects.requireNonNull(
      mapping,
      "Argument \"mapping\" must be non-null.");
    this.mappingWithConstrainedKey = Objects.requireNonNull(
      mappingWithConstrainedKey,
      "Argument \"mappingWithConstrainedKey\" must be non-null.");
  }

  public SomethingBuilder setOptionalValue(JsonNode optionalValue) {
    this.optionalValue = optionalValue;
    return this;
  }

  public SomethingBuilder setOptionalValues(ArrayNode optionalValues) {
    this.optionalValues = optionalValues;
    return this;
  }

  public SomethingBuilder setOptionalMapping(ObjectNode optionalMapping) {
    this.optionalMapping = optionalMapping;
    return this;
  }

  public Something build() {
    return new Something(
      this.value,
      this.values,
      this.mapping,
      this.mappingWithConstrainedKey,
      this.optionalValue,
      this.optionalValues,
      this.optionalMapping);
  }
}
