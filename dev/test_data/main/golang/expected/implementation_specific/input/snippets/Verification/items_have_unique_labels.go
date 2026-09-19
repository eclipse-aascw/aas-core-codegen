// Check that [aastypes.IItem.Label]'s of the `items` do not repeat.
func ItemsHaveUniqueLabels[I aastypes.IItem](items []I) bool {
	labelSet := make(map[string]struct{})

	for _, item := range items {
		label := item.Label()
		_, has := labelSet[label]
		if has {
			return false
		}

		labelSet[label] = struct{}{}
	}
	return true
}
