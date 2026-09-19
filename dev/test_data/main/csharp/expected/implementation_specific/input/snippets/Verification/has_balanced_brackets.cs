/// <summary>
/// Check that the square brackets in <paramref name="text" /> are balanced.
/// </summary>
public static bool HasBalancedBrackets(string text)
{
    int depth = 0;
    foreach (var character in text)
    {
        if (character == '[')
        {
            depth++;
        }
        else if (character == ']')
        {
            depth--;
            if (depth < 0)
            {
                return false;
            }
        }
    }
    return depth == 0;
}
