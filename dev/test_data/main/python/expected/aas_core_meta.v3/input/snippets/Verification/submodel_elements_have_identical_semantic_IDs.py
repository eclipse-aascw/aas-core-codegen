def submodel_elements_have_identical_semantic_ids(
    elements: Iterable[our_types.SubmodelElement],
) -> bool:
    """
    Check that all :paramref:`elements` have the identical
    :py:attr:`.types.HasSemantics.semantic_id`.
    """
    that_semantic_id: Optional[our_types.Reference] = None

    for element in elements:
        if element.semantic_id is None:
            continue

        if that_semantic_id is None:
            that_semantic_id = element.semantic_id
            continue

        this_semantic_id = element.semantic_id

        if len(that_semantic_id.keys) != len(this_semantic_id.keys):
            return False

        for this_key, that_key in zip(this_semantic_id.keys, that_semantic_id.keys):
            if this_key.value != that_key.value:
                return False

    return True
