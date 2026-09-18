/**
* Check that {@link IItem#getLabel() label}'s of the items do not repeat.
* @param items the items to be checked
*/
public static boolean itemsHaveUniqueLabels(Iterable<? extends IItem> items) {
  Objects.requireNonNull(items);

  Set<String> labelSet = new HashSet<>();
  for (IItem item : items) {
    if (labelSet.contains(item.getLabel())) {
      return false;
    }
    labelSet.add(item.getLabel());
  }
  return true;
}
