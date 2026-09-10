package aas_core.aas3_0.generation;

import aas_core.aas3_0.common.*;
import aas_core.aas3_0.types.enums.*;
import aas_core.aas3_0.types.impl.*;
import aas_core.aas3_0.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the Resource type.
 */
public class ResourceBuilder {
  /**
   * Path and name of the resource (with file extension).
   *
   * <p>The path can be absolute or relative.
   */
  private String path;

  /**
   * Content type of the content of the file.
   *
   * <p>The content type states which file extensions the file can have.
   */
  private String contentType;

  public ResourceBuilder(String path) {
    this.path = Objects.requireNonNull(
      path,
      "Argument \"path\" must be non-null.");
  }

  public ResourceBuilder setContentType(String contentType) {
    this.contentType = contentType;
    return this;
  }

  public Resource build() {
    return new Resource(
      this.path,
      this.contentType);
  }
}
