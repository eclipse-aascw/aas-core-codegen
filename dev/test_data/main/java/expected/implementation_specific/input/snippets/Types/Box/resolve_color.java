/**
 * @param fallback used if the color has not been set
 * @return the color if set, or the fallback otherwise.
 */
public Color resolveColor(Optional<Color> fallback) {
  if (color != null) {
    return color;
  }

  return fallback.orElse(Color.RED);
}
