def has_balanced_brackets(text: str) -> bool:
    """Check that the square brackets in :paramref:`text` are balanced."""
    depth = 0
    for character in text:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth < 0:
                return False

    return depth == 0
