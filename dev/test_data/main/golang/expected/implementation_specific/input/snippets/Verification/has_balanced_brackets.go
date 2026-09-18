// Check that the square brackets in `text` are balanced.
func HasBalancedBrackets(text string) bool {
	depth := 0
	for _, character := range text {
		if character == '[' {
			depth++
		} else if character == ']' {
			depth--
			if depth < 0 {
				return false
			}
		}
	}

	return depth == 0
}
