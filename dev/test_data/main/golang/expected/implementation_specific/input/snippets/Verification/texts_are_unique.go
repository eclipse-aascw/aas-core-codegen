// Check that the `texts` do not repeat.
func TextsAreUnique(texts []string) bool {
	textSet := make(map[string]struct{})

	for _, text := range texts {
		_, has := textSet[text]
		if has {
			return false
		}

		textSet[text] = struct{}{}
	}
	return true
}
