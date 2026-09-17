var zero *big.Int = big.NewInt(0)
var one *big.Int = big.NewInt(1)
var four *big.Int = big.NewInt(4)
var hundred *big.Int = big.NewInt(100)
var fourHundred *big.Int = big.NewInt(400)

// Check if `year` is a leap year.
func isLeapYear(year *big.Int) bool {
	// We consider the years B.C. to be one-off.
	//
	// See the note at: https://www.w3.org/TR/xmlschema-2/#dateTime:
	// "'-0001' is the lexical representation of the year 1 Before Common Era
	// (1 BCE, sometimes written "1 BC")."
	//
	// Hence, -1 year in XML is 1 BCE, which is 0 year in astronomical years.

	if year.Cmp(zero) < 0 {
		// year = -year - 1
		year.Neg(year)
		year.Sub(year, one)
	}

	// See: https://en.wikipedia.org/wiki/Leap_year#Algorithm
	yearMod4 := &big.Int{}
	yearMod4.Mod(year, four)

	if yearMod4.Cmp(zero) != 0 {
		return false
	}

	yearMod100 := &big.Int{}
	yearMod100.Mod(year, hundred)
	if yearMod100.Cmp(zero) != 0 {
		return true
	}

	yearMod400 := &big.Int{}
	yearMod400.Mod(year, fourHundred)
	if yearMod400.Cmp(zero) != 0 {
		return false
	}

	return true
}

var daysInMonth = []int{
	// Month 0 is not defined.
	-1, // 0
	31, // 1
	// Please use isLeapYear if you need to check whether
	// a concrete February has 28 or 29 days.
	29, // 2
	31, // 3
	30, // 4
	31, // 5
	30, // 6
	31, // 7
	31, // 8
	30, // 9
	31, // 10
	30, // 11
	31, // 12
}

var datePrefixRe = regexp.MustCompile("^(-?[0-9]+)-([0-9]{2})-([0-9]{2})")

// Check that `value` is a valid `xs:date`.
//
// The year must fit in the 64-bit range so that we can check whether it is
// a leap year or not.
func IsXsDate(value string) bool {
	if !MatchesXsDate(value) {
		return false
	}

	// NOTE (mristin):
	// We can not use the date functions from the standard library as we have
	// to handle years BCE according to the XML date type.

	// NOTE (mristin):
    // We need to match the prefix as zone offsets are allowed in the dates. Optimally,
    // we would re-use the pattern matching from `MatchesXsDate`, but this
    // would make the code generation and constraint inference for schemas much more
    // difficult. Hence, we sacrifice the efficiency a bit for the clearer code & code
    // generation.

	match := datePrefixRe.FindStringSubmatch(value)
	if len(match) == 0 {
		panic(
			fmt.Sprintf(
				"Expected value to match %v if we got thus far, " +
				"but it does not: %s",
				datePrefixRe, value,
			),
		)
	}

	yearStr := match[1]
	monthStr := match[2]
	dayStr := match[3]

	year := &big.Int{}
	_, ok := year.SetString(yearStr, 10)
	if !ok {
		panic(
			fmt.Sprintf(
				"Failed to convert the year from %s",
				yearStr,
			),
		)
	}

	month, err := strconv.Atoi(monthStr)
	if err != nil {
		panic(
			fmt.Sprintf(
				"Failed to convert the month from %s: %s",
				monthStr, err.Error(),
			),
		)
	}

	var day int
	day, err = strconv.Atoi(dayStr)
	if err != nil {
		panic(
			fmt.Sprintf(
				"Failed to convert the day from %s: %s",
				dayStr, err.Error(),
			),
		)
	}

	// We do not accept year zero,
	// see the note at: https://www.w3.org/TR/xmlschema-2/#dateTime
	if year.Cmp(zero) == 0 {
		return false
	}

	if day <= 0 {
		return false
	}

	if month <= 0 || month >= 13 {
		return false
	}

	var maxDays int
	if month == 2 {
		if isLeapYear(year) {
			maxDays = 29
		} else {
			maxDays = 28
		}
	} else {
		maxDays = daysInMonth[month]
	}

	if day > maxDays {
		return false
	}

	return true
}

// Check that `value` is a valid `xs:double`.
func IsXsDouble(value string) bool {
	// We need to check explicitly for the regular expression since
	// strconv.ParseFloat is too permissive. For example, it accepts "nan"
	// although only "NaN" is valid.
	// See: https://www.w3.org/TR/xmlschema-2/#double
	if !MatchesXsDouble(value) {
		return false
	}

	_, err := strconv.ParseFloat(value, 64)
	if err != nil {
		if numError, ok := err.(*strconv.NumError); ok {
            if numError.Err == strconv.ErrRange {
                return false
            }
        }

		panic(
			fmt.Sprintf(
				"Failed to parse float from value %s: %s",
				value, err.Error(),
			),
		)
	}

	// NOTE:
	// We explicitly do not check for loss of precision, as the majority of people will
	// use string representation of the floating point numbers ignoring the precision
	// issues. For example, the closest double-precision number to the number `359.9` is
	// `359.8999999999999772626324556767940521240234375`, but most people will simply
	// give `359.9` as the value.

	return true
}

// Check that `value` is a valid `xs:float`.
func IsXsFloat(value string) bool {
	// We need to check explicitly for the regular expression since
	// strconv.ParseFloat is too permissive. For example, it accepts "nan"
	// although only "NaN" is valid.
	// See: https://www.w3.org/TR/xmlschema-2/#double
	if !MatchesXsDouble(value) {
		return false
	}

	_, err := strconv.ParseFloat(value, 32)
	if err != nil {
        if numError, ok := err.(*strconv.NumError); ok {
            if numError.Err == strconv.ErrRange {
                return false
            }
        }

		panic(
			fmt.Sprintf(
				"Failed to parse float from value %s: %s",
				value, err.Error(),
			),
		)
	}

	// NOTE:
	// We explicitly do not check for loss of precision, as the majority of people will
	// use string representation of the floating point numbers ignoring the precision
	// issues. For example, `float64(float32(3.2)) == 3.2` is false in Golang, but "3.2"
	// is totally expected as a value.

	return true
}

// Check that `value` is a valid `xs:gMonthDay`.
func IsXsGMonthDay(value string) bool {
	if !MatchesXsGMonthDay(value) {
		return false
	}

	month, err := strconv.Atoi(value[2:4])
	if err != nil {
		panic(
			fmt.Sprintf(
				"Unexpected fail to parse the month %s: %s",
				value[2:4], err.Error(),
			),
		)
	}

	var day int
	day, err = strconv.Atoi(value[5:7])
	if err != nil {
		panic(
			fmt.Sprintf(
				"Unexpected fail to parse the day %s: %s",
				value[5:7], err.Error(),
			),
		)
	}

	maxDays := daysInMonth[month]
	return day <= maxDays
}

// Check that `value` is a valid `xs:long`.
func IsXsLong(value string) bool {
	if !MatchesXsLong(value) {
		return false
	}

	_, err := strconv.ParseInt(value, 10, 64)
	return err == nil
}

// Check that `value` is a valid `xs:int`.
func IsXsInt(value string) bool {
	if !MatchesXsInt(value) {
		return false
	}

	_, err := strconv.ParseInt(value, 10, 32)
	return err == nil
}

// Check that `value` is a valid `xs:short`.
func IsXsShort(value string) bool {
	if !MatchesXsShort(value) {
		return false
	}

	_, err := strconv.ParseInt(value, 10, 16)
	return err == nil
}

// Check that `value` is a valid `xs:byte`.
func IsXsByte(value string) bool {
	if !MatchesXsByte(value) {
		return false
	}

	_, err := strconv.ParseInt(value, 10, 8)
	return err == nil
}

// Check that `value` is a valid `xs:unsignedLong`.
func IsXsUnsignedLong(value string) bool {
	if !MatchesXsUnsignedLong(value) {
		return false
	}

	// See: https://pkg.go.dev/strconv#ParseUint,
	// "A sign prefix is not permitted."
	if value[0] == '+' {
		value = value[1:]
	}

	_, err := strconv.ParseUint(value, 10, 64)
	return err == nil
}

// Check that `value` is a valid `xs:unsignedInt`.
func IsXsUnsignedInt(value string) bool {
	if !MatchesXsUnsignedInt(value) {
		return false
	}

	// See: https://pkg.go.dev/strconv#ParseUint,
	// "A sign prefix is not permitted."
	if value[0] == '+' {
		value = value[1:]
	}

	_, err := strconv.ParseUint(value, 10, 32)
	return err == nil
}

// Check that `value` is a valid `xs:unsignedShort`.
func IsXsUnsignedShort(value string) bool {
	if !MatchesXsUnsignedShort(value) {
		return false
	}

	// See: https://pkg.go.dev/strconv#ParseUint,
	// "A sign prefix is not permitted."
	if value[0] == '+' {
		value = value[1:]
	}

	_, err := strconv.ParseUint(value, 10, 16)
	return err == nil
}

// Check that `value` is a valid `xs:unsignedByte`.
func IsXsUnsignedByte(value string) bool {
	if !MatchesXsUnsignedByte(value) {
		return false
	}

	// See: https://pkg.go.dev/strconv#ParseUint,
	// "A sign prefix is not permitted."
	if value[0] == '+' {
		value = value[1:]
	}

	_, err := strconv.ParseUint(value, 10, 8)
	return err == nil
}

// Check that `value` is consistent with the given `valueType`.
func ValueConsistentWithXSDType(
	value string,
	valueType aastypes.DataTypeDefXSD,
) bool {
	switch valueType {
		case aastypes.DataTypeDefXSDAnyURI:
			return MatchesXsAnyURI(value)
		case aastypes.DataTypeDefXSDBase64Binary:
			return MatchesXsBase64Binary(value)
		case aastypes.DataTypeDefXSDBoolean:
			return MatchesXsBoolean(value)
		case aastypes.DataTypeDefXSDByte:
			return IsXsByte(value)
		case aastypes.DataTypeDefXSDDate:
			return IsXsDate(value)
		case aastypes.DataTypeDefXSDDateTime:
			return IsXsDateTime(value)
		case aastypes.DataTypeDefXSDDecimal:
			return MatchesXsDecimal(value)
		case aastypes.DataTypeDefXSDDouble:
			return IsXsDouble(value)
		case aastypes.DataTypeDefXSDDuration:
			return MatchesXsDuration(value)
		case aastypes.DataTypeDefXSDFloat:
		 	return IsXsFloat(value)
		case aastypes.DataTypeDefXSDGDay:
			return MatchesXsGDay(value)
		case aastypes.DataTypeDefXSDGMonth:
			return MatchesXsGMonth(value)
		case aastypes.DataTypeDefXSDGMonthDay:
			return IsXsGMonthDay(value)
		case aastypes.DataTypeDefXSDGYear:
			return MatchesXsGYear(value)
		case aastypes.DataTypeDefXSDGYearMonth:
			return MatchesXsGYearMonth(value)
		case aastypes.DataTypeDefXSDHexBinary:
			return MatchesXsHexBinary(value)
		case aastypes.DataTypeDefXSDInt:
			return IsXsInt(value)
		case aastypes.DataTypeDefXSDInteger:
			return MatchesXsInteger(value)
		case aastypes.DataTypeDefXSDLong:
			return IsXsLong(value)
		case aastypes.DataTypeDefXSDNegativeInteger:
			return MatchesXsNegativeInteger(value)
		case aastypes.DataTypeDefXSDNonNegativeInteger:
			return MatchesXsNonNegativeInteger(value)
		case aastypes.DataTypeDefXSDNonPositiveInteger:
			return MatchesXsNonPositiveInteger(value)
		case aastypes.DataTypeDefXSDPositiveInteger:
			return MatchesXsPositiveInteger(value)
		case aastypes.DataTypeDefXSDShort:
			return IsXsShort(value)
		case aastypes.DataTypeDefXSDString:
			return MatchesXsString(value)
		case aastypes.DataTypeDefXSDTime:
			return MatchesXsTime(value)
		case aastypes.DataTypeDefXSDUnsignedByte:
			return IsXsUnsignedByte(value)
		case aastypes.DataTypeDefXSDUnsignedInt:
			return IsXsUnsignedInt(value)
		case aastypes.DataTypeDefXSDUnsignedLong:
			return IsXsUnsignedLong(value)
		case aastypes.DataTypeDefXSDUnsignedShort:
			return IsXsUnsignedShort(value)
		default:
			panic(fmt.Sprintf("Unhandled value type: %v", valueType))
	}
}
