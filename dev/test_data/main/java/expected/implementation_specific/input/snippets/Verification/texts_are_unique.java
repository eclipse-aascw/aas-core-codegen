/**
* Check that the texts do not repeat.
* @param texts the texts to be checked
*/
public static boolean textsAreUnique(Iterable<String> texts) {
  Objects.requireNonNull(texts);

  Set<String> textSet = new HashSet<>();
  for (String text : texts) {
    if (textSet.contains(text)) {
      return false;
    }
    textSet.add(text);
  }
  return true;
}
