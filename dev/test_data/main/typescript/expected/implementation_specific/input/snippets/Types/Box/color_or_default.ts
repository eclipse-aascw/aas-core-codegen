/**
 * @returns {@link color} if set, or the default otherwise.
 */
colorOrDefault(): Color {
    return (this.color !== null) ? this.color : Color.Red;
}
