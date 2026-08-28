def test_filter_repository_crud(filter_repository):
    filter_repository.create_filter("Test Filter", "credit_score > 600")
    filters = filter_repository.get_filters()
    assert len(filters) == 1
    fid = next(iter(filters.keys()))

    # Modify
    filter_repository.modify_filter(
        fid, name="Updated Filter", query="credit_score > 650"
    )
    updated_filters = filter_repository.get_filters()
    assert len(updated_filters) == 1
    new_fid = next(iter(updated_filters.keys()))

    # Verify ID changed
    assert new_fid != fid

    # Duplicate
    filter_repository.duplicate_filter(new_fid)
    assert len(filter_repository.get_filters()) == 2

    # Remove
    filter_repository.remove_filter(new_fid)
    assert len(filter_repository.get_filters()) == 1
