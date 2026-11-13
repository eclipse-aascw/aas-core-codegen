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
  private IItem item;

  private String optionalText;

  private Long optionalNumber;

  private IItem optionalItem;

  private List<String> optionalTexts;

  private Kind optionalKind;

  private Boolean optionalFlag;

  public SomethingBuilder(IItem item) {
    this.item = Objects.requireNonNull(
      item,
      "Argument \"item\" must be non-null.");
  }

  public SomethingBuilder setOptionalText(String optionalText) {
    this.optionalText = optionalText;
    return this;
  }

  public SomethingBuilder setOptionalNumber(Long optionalNumber) {
    this.optionalNumber = optionalNumber;
    return this;
  }

  public SomethingBuilder setOptionalItem(IItem optionalItem) {
    this.optionalItem = optionalItem;
    return this;
  }

  public SomethingBuilder setOptionalTexts(List<String> optionalTexts) {
    this.optionalTexts = optionalTexts;
    return this;
  }

  public SomethingBuilder setOptionalKind(Kind optionalKind) {
    this.optionalKind = optionalKind;
    return this;
  }

  public SomethingBuilder setOptionalFlag(Boolean optionalFlag) {
    this.optionalFlag = optionalFlag;
    return this;
  }

  public Something build() {
    return new Something(
      this.item,
      this.optionalText,
      this.optionalNumber,
      this.optionalItem,
      this.optionalTexts,
      this.optionalKind,
      this.optionalFlag);
  }
}
