// Return the color, or the `fallback` if the color has not been set.
func (_RECEIVER_ *_STRUCT_NAME_) ResolveColor(fallback *Color) Color {
	c := _RECEIVER_.Color()
	if c != nil {
		return *c
	}

	if fallback != nil {
		return *fallback
	}

	return ColorRed
}
