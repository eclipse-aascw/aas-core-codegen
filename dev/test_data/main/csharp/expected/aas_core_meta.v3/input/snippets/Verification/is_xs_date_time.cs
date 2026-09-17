private static readonly Regex RegexDatePrefix = (
    new Regex("^(-?[0-9]+)-([0-9]{2})-([0-9]{2})"));

/// <summary>
/// Check whether the given year is a leap year.
/// </summary>
/// <remarks>Year 1 BCE is a leap year.</remarks>
/// <param name="year">to be checked</param>
/// <returns>True if <paramref name="year"/> is a leap year</returns>
public static bool IsLeapYear(System.Numerics.BigInteger year)
{
    // NOTE (mristin):
    // We consider the years B.C. to be one-off.
    // See the note at: https://www.w3.org/TR/xmlschema-2/#dateTime:
    // "'-0001' is the lexical representation of the year 1 Before Common Era
    // (1 BCE, sometimes written "1 BC")."
    //
    // Hence, -1 year in XML is 1 BCE, which is 0 year in astronomical years.
    if (year < 0)
    {
        year = -year - 1;
    }

    // See: See: https://en.wikipedia.org/wiki/Leap_year#Algorithm
    if (year % 4 > 0)
    {
        return false;
    }

    if (year % 100 > 0)
    {
        return true;
    }

    if (year % 400 > 0)
    {
        return false;
    }

    return true;
}

/// <summary>
/// Check that the value starts with a valid date.
/// </summary>
/// <param name="value">
///     an <c>xs:date</c>, an <c>xs:dateTime</c>,
///     or an <c>xs:dateTimeStamp</c></param>
/// <returns>
///     <c>true</c> if the value starts with a valid date
/// </returns>
private static bool IsPrefixedWithValidDate(string value)
{
    // NOTE (mristin):
    // We can not use System.DateTime.ParseExact since it does not handle the zero and
    // BCE years correctly. Therefore, we have to roll out our own date validator.
    var match = RegexDatePrefix.Match(value);
    if (!match.Success)
    {
        return false;
    }

    bool ok = System.Numerics.BigInteger.TryParse(
        match.Groups[1].Value,
        out System.Numerics.BigInteger year);
    if (!ok)
    {
        throw new System.InvalidOperationException(
            $"Expected to parse the year from {match.Groups[1].Value}, " +
            "but the parsing failed");
    }

    ok = System.SByte.TryParse(match.Groups[2].Value, out sbyte month);
    if (!ok)
    {
        throw new System.InvalidOperationException(
            $"Expected to parse the month from {match.Groups[2].Value}, " +
            "but the parsing failed");
    }

    ok = System.SByte.TryParse(match.Groups[3].Value, out sbyte day);
    if (!ok)
    {
        throw new System.InvalidOperationException(
            $"Expected to parse the day from {match.Groups[3].Value}, " +
            "but the parsing failed");
    }

    // Year zero does not exist, see: https://www.w3.org/TR/xmlschema-2/#dateTime
    if (year == 0)
    {
        return false;
    }

    if (day <= 0 || day > 31)
    {
        return false;
    }

    if (month <= 0 || month >= 13)
    {
        return false;
    }

    sbyte maxDaysInMonth;
    switch (month)
    {
        case 1:
            maxDaysInMonth = 31;
            break;
        case 2:
            maxDaysInMonth = (IsLeapYear(year)) ? (sbyte)29 : (sbyte)28;
            break;
        case 3:
            maxDaysInMonth = 31;
            break;
        case 4:
            maxDaysInMonth = 30;
            break;
        case 5:
            maxDaysInMonth = 31;
            break;
        case 6:
            maxDaysInMonth = 30;
            break;
        case 7:
            maxDaysInMonth = 31;
            break;
        case 8:
            maxDaysInMonth = 31;
            break;
        case 9:
            maxDaysInMonth = 30;
            break;
        case 10:
            maxDaysInMonth = 31;
            break;
        case 11:
            maxDaysInMonth = 30;
            break;
        case 12:
            maxDaysInMonth = 31;
            break;
        default:
            throw new System.InvalidOperationException($"Unexpected month: {month}");
    }

    if (day > maxDaysInMonth)
    {
        return false;
    }

    return true;
}

/// <summary>
/// Check that <paramref name="value" /> is a <c>xs:dateTime</c> with
/// the time zone set to UTC.
/// </summary>
public static bool IsXsDateTime(
    string value
)
{
    if (!MatchesXsDateTime(value))
    {
        return false;
    }

    return IsPrefixedWithValidDate(value);
}
