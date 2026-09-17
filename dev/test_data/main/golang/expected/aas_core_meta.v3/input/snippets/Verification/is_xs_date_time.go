// Check that `value` is a valid `xs:dateTime`.
//
// Year 1 BCE is the last leap BCE year.
// See https://www.w3.org/TR/xmlschema-2/#dateTime.
func IsXsDateTime(value string) bool {
	// NOTE (mristin):
  	// We can not use date functions from the standard library as it does not
	// handle years BCE (*e.g.*, `-0003-01-02`).

	if !MatchesXsDateTime(value) {
		return false
	}

	date, _, ok := strings.Cut(value, "T")
	if !ok {
		panic(
			fmt.Sprintf(
				"Expected 'T' in the date-time if it matches the expected regex, " +
				"but got: %s",
				value,
			),
		)
	}
	return IsXsDate(date)
}
