/// <summary>
/// Return the <see cref="Color" />, or the <paramref name="fallback" />
/// if it has not been set.
/// </summary>
public Color ResolveColor(Color? fallback)
{
    return Color ?? fallback ?? Aas.Color.Red;
}
