/**
 * @param fallback - used if {@link color} has not been set
 * @returns {@link color} if set, or the `fallback` otherwise.
 */
resolveColor(fallback: Color | null): Color {
    if (this.color !== null) {
        return this.color;
    }

    return (fallback !== null) ? fallback : Color.Red;
}
