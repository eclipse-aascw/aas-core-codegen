package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the IecContent type.
 */
public class IecContentBuilder {
  private List<ILangString> definition;

  public IecContentBuilder setDefinition(List<ILangString> definition) {
    this.definition = definition;
    return this;
  }

  public IecContent build() {
    return new IecContent(this.definition);
  }
}
