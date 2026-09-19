def items_have_unique_labels(items: Iterable[aas_types.Item]) -> bool:
    """
    Check that :py:attr:`.types.Item.label`'s of the :paramref:`items`
    do not repeat.
    """
    label_set = set()  # type: Set[str]
    for item in items:
        if item.label in label_set:
            return False

        label_set.add(item.label)

    return True
