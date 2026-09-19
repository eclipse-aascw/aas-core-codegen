/**
 * Check that the `texts` do not repeat.
 *
 * @param texts - to be verified
 * @returns `true` if the check passes
 */
export function textsAreUnique(texts: Iterable<string>): boolean {
  const textSet = new Set<string>();
  for (const text of texts) {
    if (textSet.has(text)) {
      return false;
    }

    textSet.add(text);
  }

  return true;
}
