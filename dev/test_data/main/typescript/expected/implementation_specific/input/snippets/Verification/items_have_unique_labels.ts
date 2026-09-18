/**
 * Check that {@link types.IItem.label}'s of the `items` do not repeat.
 *
 * @param items - to be verified
 * @returns `true` if the check passes
 */
export function itemsHaveUniqueLabels(
  items: Iterable<AasTypes.IItem>
): boolean {
  const labelSet = new Set<string>();
  for (const item of items) {
    if (labelSet.has(item.label)) {
      return false;
    }

    labelSet.add(item.label);
  }

  return true;
}
