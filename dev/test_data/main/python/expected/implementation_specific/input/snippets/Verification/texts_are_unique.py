def texts_are_unique(texts: Iterable[str]) -> bool:
    """Check that the :paramref:`texts` do not repeat."""
    text_set: Set[str] = set()
    for text in texts:
        if text in text_set:
            return False

        text_set.add(text)

    return True
