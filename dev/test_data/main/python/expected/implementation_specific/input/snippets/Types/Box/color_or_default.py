def color_or_default(self) -> "Color":
    """Return the :py:attr:`color` if set, or the default otherwise."""
    return self.color if self.color is not None else Color.RED
