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
  private String defaultLanguage;

  private List<ILangStringSet> langStringSets;

  private List<ISpecification> specifications;

  public SomethingBuilder(
    String defaultLanguage,
    List<ILangStringSet> langStringSets) {
    this.defaultLanguage = Objects.requireNonNull(
      defaultLanguage,
      "Argument \"defaultLanguage\" must be non-null.");
    this.langStringSets = Objects.requireNonNull(
      langStringSets,
      "Argument \"langStringSets\" must be non-null.");
  }

  public SomethingBuilder setSpecifications(List<ISpecification> specifications) {
    this.specifications = specifications;
    return this;
  }

  public Something build() {
    return new Something(
      this.defaultLanguage,
      this.langStringSets,
      this.specifications);
  }
}
