/// <summary>
/// Check that the <paramref name="texts" /> do not repeat.
/// </summary>
public static bool TextsAreUnique(IEnumerable<string> texts)
{
    var textSet = new HashSet<string>();
    foreach (var text in texts)
    {
        if (textSet.Contains(text))
        {
            return false;
        }
        textSet.Add(text);
    }
    return true;
}
