/**
 * Check that `value` is a valid `xs:dateTime`.
 *
 * @remarks
 * Year 1 BCE is the last leap BCE year.
 * See https://www.w3.org/TR/xmlschema-2/#dateTime.
 *
 * @param value - to be be checked
 * @returns `true` if `value` is a valid `xs:dateTime`
 */
export function isXsDateTime(value: string): boolean {
  // NOTE (mristin):
  // We can not use date functions from the standard library as it does not
  // handle years BCE (*e.g.*, `-0003-01-02`).

  if (!matchesXsDateTime(value)) {
    return false;
  }

  const date = value.split("T", 1)[0];
  return isXsDate(date);
}
