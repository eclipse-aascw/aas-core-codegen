package dummy.generation;

import dummy.common.*;
import dummy.types.enums.*;
import dummy.types.impl.*;
import dummy.types.model.*;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Builder for the QueryCondition type.
 */
public class QueryConditionBuilder {
  /**
   * Operand to be checked for equality.
   */
  private String eq;

  /**
   * Operand to be checked for inequality.
   */
  private String notEq;

  public QueryConditionBuilder setEq(String eq) {
    this.eq = eq;
    return this;
  }

  public QueryConditionBuilder setNotEq(String notEq) {
    this.notEq = notEq;
    return this;
  }

  public QueryCondition build() {
    return new QueryCondition(
      this.eq,
      this.notEq);
  }
}
