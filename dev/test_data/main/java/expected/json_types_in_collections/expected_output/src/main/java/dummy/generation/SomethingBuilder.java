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
  private List<JsonNode> values;

  private Tuple4<String, JsonNode, ArrayNode, ObjectNode> tupleWithJson;

  private List<ObjectNode> optionalObjects;

  private ObjectNode optionalObject;

  public SomethingBuilder(
    List<JsonNode> values,
    Tuple4<String, JsonNode, ArrayNode, ObjectNode> tupleWithJson) {
    this.values = Objects.requireNonNull(
      values,
      "Argument \"values\" must be non-null.");
    this.tupleWithJson = Objects.requireNonNull(
      tupleWithJson,
      "Argument \"tupleWithJson\" must be non-null.");
  }

  public SomethingBuilder setOptionalObjects(List<ObjectNode> optionalObjects) {
    this.optionalObjects = optionalObjects;
    return this;
  }

  public SomethingBuilder setOptionalObject(ObjectNode optionalObject) {
    this.optionalObject = optionalObject;
    return this;
  }

  public Something build() {
    return new Something(
      this.values,
      this.tupleWithJson,
      this.optionalObjects,
      this.optionalObject);
  }
}
