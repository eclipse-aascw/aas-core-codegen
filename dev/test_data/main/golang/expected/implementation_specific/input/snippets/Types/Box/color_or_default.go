// Return the color if set, or the default otherwise.
func (_RECEIVER_ *_STRUCT_NAME_) ColorOrDefault() Color {
	c := _RECEIVER_.Color()
	if c == nil {
		return ColorRed
	}

	return *c
}
