def resolve_color(self, fallback: Optional["Color"]) -> "Color":
    """Return the :py:attr:`color`, or the :paramref:`fallback` if not set."""
    if self.color is not None:
        return self.color

    return fallback if fallback is not None else Color.RED
