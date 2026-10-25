def extension_names_are_unique(extensions: Iterable[our_types.Extension]) -> bool:
    """
    Check that all :py:attr:`.types.Extension.name` are unique
    among :paramref:`extensions`.
    """
    name_set: Set[str] = set()
    for extension in extensions:
        if extension.name in name_set:
            return False

        name_set.add(extension.name)

    return True
