/// <summary>
/// Return the <see cref="Color" /> if set, or the default otherwise.
/// </summary>
public Color ColorOrDefault()
{
    return Color ?? Aas.Color.Red;
}
