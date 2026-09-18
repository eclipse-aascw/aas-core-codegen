/// <summary>
/// Check that <see cref="Aas.IItem.Label" />'s of the <paramref name="items" />
/// do not repeat.
/// </summary>
public static bool ItemsHaveUniqueLabels(IEnumerable<Aas.IItem> items)
{
    var labelSet = new HashSet<string>();
    foreach (var item in items)
    {
        if (labelSet.Contains(item.Label))
        {
            return false;
        }
        labelSet.Add(item.Label);
    }
    return true;
}
