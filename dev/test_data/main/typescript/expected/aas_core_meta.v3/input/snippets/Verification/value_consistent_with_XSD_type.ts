/**
 * Check if `year` is a leap year.
 *
 * @remarks
 * Year 1 BCE is the last leap BCE year.
 * See https://www.w3.org/TR/xmlschema-2/#dateTime.
 *
 * @param year - to be checked
 * @returns `true` if `year` is a leap year.
 */
export function isLeapYear(year: number): boolean {
  // We consider the years B.C. to be one-off.
  //
  // See the note at: https://www.w3.org/TR/xmlschema-2///dateTime:
  // "'-0001' is the lexical representation of the year 1 Before Common Era
  // (1 BCE, sometimes written "1 BC")."
  //
  // Hence, -1 year in XML is 1 BCE, which is 0 year in astronomical years.
  if (year < 0) {
    year = -year - 1;
  }

  // See: https://en.wikipedia.org/wiki/Leap_year#Algorithm
  if (year % 4 > 0) {
    return false;
  }

  if (year % 100 > 0) {
    return true;
  }

  if (year % 400 > 0) {
    return false;
  }

  return true;
}

const DAYS_IN_MONTH = new Map<number, number>(
  [
    [1, 31],
    // Please use isLeapYear if you need to check
    // whether a concrete February has 28 or 29 days.
    [2, 29],
    [3, 31],
    [4, 30],
    [5, 31],
    [6, 30],
    [7, 31],
    [8, 31],
    [9, 30],
    [10, 31],
    [11, 30],
    [12, 31]
  ]
);

const DATE_PREFIX_RE = new RegExp("^(-?[0-9]+)-([0-9]{2})-([0-9]{2})");

/**
 * Check that `value` is a valid `xs:date`.
 *
 * @remarks
 * Year 1 BCE is the last leap BCE year.
 * See https://www.w3.org/TR/xmlschema-2/#dateTime.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:date`
 */
export function isXsDate(value: string): boolean {
  // NOTE (mristin):
  // We can not use date functions from the standard library as it does not
  // handle years BCE (*e.g.*, `-0003-01-02`).

  if (!matchesXsDate(value)) {
    return false;
  }

  // NOTE (mristin):
  // We need to match the prefix as zone offsets are allowed in the dates. Optimally,
  // we would re-use the pattern matching from `matchesXsDate`, but this
  // would make the code generation and constraint inference for schemas much more
  // difficult. Hence, we sacrifice the efficiency a bit for the clearer code & code
  // generation.

  const match = DATE_PREFIX_RE.exec(value);

  const year = parseInt(match[1], 10);
  const month = parseInt(match[2], 10);
  const day = parseInt(match[3], 10);

  // We do not accept year zero,
  // see the note at: https://www.w3.org/TR/xmlschema-2/#dateTime
  if (year === 0) {
    return false;
  }

  if (day <= 0) {
    return false;
  }

  if (month <= 0 || month >= 13) {
    return false;
  }

  const maxDays = (month === 2)
    ? (isLeapYear(year) ? 29 : 28)
    : DAYS_IN_MONTH.get(month);

  if (day > maxDays) {
    return false;
  }

  return true;
}

/**
 * Check that `value` is a valid `xs:double`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:double`
 */
export function isXsDouble(value: string): boolean {
  // NOTE (mristin):
  // We need to check explicitly for the regular expression since
  // `parseFloat` expects `Infinity`  instead of `INF`.
  if (!matchesXsDouble(value)) {
    return false;
  }

  if (value !== "INF" && value !== "-INF" && value !== "NaN") {
    // NOTE (mristin):
    // Check that the value is not too big to be represented as a double-precision
    // floating point number.
    //
    // For example, `parseFloat("1e400")` gives `Infinity`.
    const converted = parseFloat(value);

    if (!isFinite(converted)) {
      return false;
    }
  }

  return true;
}

/**
 * Check that `value` is a valid `xs:float`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:float`
 */
export function isXsFloat(value: string): boolean {
  // NOTE (mristin):
  // We need to check explicitly for the regular expression since
  // `parseFloat` expects `Infinity`  instead of `INF`.
  if (!matchesXsFloat(value)) {
    return false;
  }

  if (value !== "INF" && value !== "-INF" && value !== "NaN") {
    // NOTE (mristin):
    // Check that the value is not too big to be represented as a double-precision
    // floating point number.
    //
    // For example, `parseFloat("1e400")` gives `Infinity`.
    const converted = parseFloat(value);

    if (!isFinite(converted)) {
      return false;
    }

    // NOTE (mristin):
    // TypeScript represents numbers as 64-bit floating point numbers. While there
    // is no easy way to deal with the precision, as precision is silently
    // gutted during the parsing, we can still check if the number is too large
    // to fit in a 32-bit float.
    const rounded = Math.fround(converted);
    if (!isFinite(rounded)) {
      return false;
    }
  }

  return true;
}

/**
 * Check that `value` is a valid `xs:gMonthDay`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:gMonthDay`
 */
export function isXsGMonthDay(value: string): boolean {
  if (!matchesXsGMonthDay(value)) {
    return false;
  }

  const month = parseInt(value.substring(2, 4), 10);
  const day = parseInt(value.substring(5, 7), 10);

  const maxDays = DAYS_IN_MONTH.get(month);
  return day <= maxDays;
}

const LONG_RE = new RegExp("^([\-+])?0*([0-9]{1,20})$");

const SMALLEST_LONG_WITHOUT_SIGN_AS_STRING = "9223372036854775808";
const LARGEST_LONG_AS_STRING = "9223372036854775807";

/**
 * Check that `value` is a valid `xs:long`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:long`
 */
export function isXsLong(value: string): boolean {
  // NOTE (mristin):
  // We need to operate on the value as string since TypeScript represents numbers as
  // 64-bit floating-point numbers which can not capture 64-bit integers.

  const match = value.match(LONG_RE);
  if (!match) {
    return false;
  }

  const numberPart = match[2];

  const limit = (match[1] === "-")
    ? SMALLEST_LONG_WITHOUT_SIGN_AS_STRING
    : LARGEST_LONG_AS_STRING;

  if (numberPart.length < limit.length) {
    return true;
  }

  if (numberPart.length > limit.length) {
    return false;
  }

  for (let i = numberPart.length - 1; i >= 0; i--) {
    const thisDigit = numberPart.charCodeAt(i);
    const limitDigit = limit.charCodeAt(i);

    if (thisDigit > limitDigit) {
      return false;
    } else if (thisDigit < limitDigit) {
      return true;
    } else {
      // Pass, we have to compare against the next digit from the left.
    }
  }

  // The number is exactly the limit.
  return true;
}

/**
 * Check that `value` is a valid `xs:int`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:int`
 */
export function isXsInt(value: string): boolean {
  if (!matchesXsInt(value)) {
    return false;
  }

  const converted = parseInt(value, 10);
  return -2147483648 <= converted && converted <= 2147483647;
}

/**
 * Check that `value` is a valid `xs:short`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:short`
 */
export function isXsShort(value: string): boolean {
  if (!matchesXsShort(value)) {
    return false;
  }

  const converted = parseInt(value, 10);
  return -32768 <= converted && converted <= 32767;
}

/**
 * Check that `value` is a valid `xs:byte`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:byte`
 */
export function isXsByte(value: string): boolean {
  if (!matchesXsByte(value)) {
    return false;
  }

  const converted = parseInt(value, 10);
  return -128 <= converted && converted <= 127;
}

const UNSIGNED_LONG_RE = new RegExp("^(-0|\\+?0*([0-9]{1,20}))$");

const LARGEST_UNSIGNED_LONG_AS_STRING = "18446744073709551615";

/**
 * Check that `value` is a valid `xs:unsignedLong`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:unsignedLong`
 */
export function isXsUnsignedLong(value: string): boolean {
  // NOTE (mristin):
  // We need to operate on the value as string since TypeScript represents numbers as
  // 64-bit floating-point numbers which can not capture 64-bit integers.

  const match = value.match(UNSIGNED_LONG_RE);
  if (!match) {
    return false;
  }

  const numberPart = match[2];

  if (numberPart.length < LARGEST_UNSIGNED_LONG_AS_STRING.length) {
    return true;
  }

  if (numberPart.length > LARGEST_UNSIGNED_LONG_AS_STRING.length) {
    return false;
  }

  for (let i = numberPart.length - 1; i >= 0; i--) {
    const thisDigit = numberPart.charCodeAt(i);
    const limitDigit = LARGEST_UNSIGNED_LONG_AS_STRING.charCodeAt(i);

    if (thisDigit > limitDigit) {
      return false;
    } else if (thisDigit < limitDigit) {
      return true;
    } else {
      // Pass, we have to compare against the next digit from the left.
    }
  }

  // The number is exactly the limit.
  return true;
}

/**
 * Check that `value` is a valid `xs:unsignedInt`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:unsignedInt`
 */
export function isXsUnsignedInt(value: string): boolean {
  if (!matchesXsUnsignedInt(value)) {
    return false;
  }

  const converted = parseInt(value, 10);
  return 0 <= converted && converted <= 4294967295;
}

/**
 * Check that `value` is a valid `xs:unsignedShort`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:unsignedShort`
 */
export function isXsUnsignedShort(value: string): boolean {
  if (!matchesXsUnsignedShort(value)) {
    return false;
  }

  const converted = parseInt(value, 10);
  return 0 <= converted && converted <= 65535;
}

/**
 * Check that `value` is a valid `xs:unsignedByte`.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:unsignedByte`
 */
export function isXsUnsignedByte(value: string): boolean {
  if (!matchesXsUnsignedByte(value)) {
    return false;
  }

  const converted = parseInt(value, 10);
  return 0 <= converted && converted <= 255;
}


// NOTE (mristin):
// The literals of AasTypes.DataTypeDefXsd are consecutive integers starting
// at 0, so we index into an array instead of looking the check up in a map.
const DATA_TYPE_DEF_XSD_TO_VALUE_CONSISTENCY: ReadonlyArray<
  (value: string) => boolean
> = [
  matchesXsAnyUri, // AnyUri
  matchesXsBase64Binary, // Base64Binary
  matchesXsBoolean, // Boolean
  isXsByte, // Byte
  isXsDate, // Date
  isXsDateTime, // DateTime
  matchesXsDecimal, // Decimal
  isXsDouble, // Double
  matchesXsDuration, // Duration
  isXsFloat, // Float
  matchesXsGDay, // GDay
  matchesXsGMonth, // GMonth
  isXsGMonthDay, // GMonthDay
  matchesXsGYear, // GYear
  matchesXsGYearMonth, // GYearMonth
  matchesXsHexBinary, // HexBinary
  isXsInt, // Int
  matchesXsInteger, // Integer
  isXsLong, // Long
  matchesXsNegativeInteger, // NegativeInteger
  matchesXsNonNegativeInteger, // NonNegativeInteger
  matchesXsNonPositiveInteger, // NonPositiveInteger
  matchesXsPositiveInteger, // PositiveInteger
  isXsShort, // Short
  matchesXsString, // String
  matchesXsTime, // Time
  isXsUnsignedByte, // UnsignedByte
  isXsUnsignedInt, // UnsignedInt
  isXsUnsignedLong, // UnsignedLong
  isXsUnsignedShort // UnsignedShort
];

function assertAllDataTypeDefXsdCovered() {
  for (const literal of AasTypes.overDataTypeDefXsd()) {
    if (DATA_TYPE_DEF_XSD_TO_VALUE_CONSISTENCY[literal] === undefined) {
      throw new Error(
        `The enumeration key ${literal} of AasTypes.DataTypeDefXsd ` +
          "is not covered in DATA_TYPE_DEF_XSD_TO_VALUE_CONSISTENCY"
      );
    }
  }
}
assertAllDataTypeDefXsdCovered();

/**
 * Check that `value` is consistent with the given `valueType`.
 *
 * @param value - expected to be consistent with `valueType`
 * @param valueType - expected XSD type of `value`
 * @returns `true` if `value` consistent with `valueType`
 */
export function valueConsistentWithXsdType(
  value: string,
  valueType: AasTypes.DataTypeDefXsd
): boolean {
  const verifier = DATA_TYPE_DEF_XSD_TO_VALUE_CONSISTENCY[valueType];
  if (verifier === undefined) {
    throw new Error(
      "The value type is invalid. Expected a literal of DataTypeDefXsd, " +
      `but got: ${valueType}`
    );
  }
  return verifier(value);
}
