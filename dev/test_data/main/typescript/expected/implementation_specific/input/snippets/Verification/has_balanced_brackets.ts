/**
 * Check that the square brackets in `text` are balanced.
 *
 * @param text - to be verified
 * @returns `true` if the check passes
 */
export function hasBalancedBrackets(text: string): boolean {
  let depth = 0;
  for (const character of text) {
    if (character === "[") {
      depth++;
    } else if (character === "]") {
      depth--;
      if (depth < 0) {
        return false;
      }
    }
  }

  return depth === 0;
}
