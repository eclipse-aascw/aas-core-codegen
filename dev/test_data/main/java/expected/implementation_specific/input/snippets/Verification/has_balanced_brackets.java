/**
* Check that the square brackets in the text are balanced.
* @param text the text to be checked
*/
public static boolean hasBalancedBrackets(String text) {
  Objects.requireNonNull(text);

  int depth = 0;
  for (int i = 0; i < text.length(); i++) {
    final char character = text.charAt(i);
    if (character == '[') {
      depth++;
    } else if (character == ']') {
      depth--;
      if (depth < 0) {
        return false;
      }
    }
  }
  return depth == 0;
}
